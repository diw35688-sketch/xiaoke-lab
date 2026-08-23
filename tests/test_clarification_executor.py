"""ClarificationExecutor 测试：施工单到真实状态的完整映射。"""

import unittest

from src.core.clarification_acceptance import (
    ClarificationAction,
    ClarificationActionType,
    ClarificationMutationPermission,
)
from src.core.clarification_executor import (
    AnswerEntityExtractor,
    ClarificationExecutionResult,
    ClarificationExecutor,
)
from src.core.reply_coordinator import ReplyCoordinator


class FakeEntityExtractor:
    """测试用实体提取器——不调 LLM，返回预设字段名。"""

    def __init__(self, fields=None, error=None):
        self.fields = fields or set()
        self.error = error
        self.calls = []

    def extract(self, answer_text: str) -> set[str]:
        self.calls.append(answer_text)
        if self.error:
            raise self.error
        return set(self.fields)


def _action(**overrides):
    defaults = {
        "request_id": "req-1",
        "session_id": "session-1",
        "segment_id": 1,
        "asr_transcript": "将溶液加热。",
        "action_type": ClarificationActionType.NO_ACTION,
        "mutation_permission": ClarificationMutationPermission.NONE,
        "reason": "测试施工单。",
        "requires_evidence_persistence": False,
    }
    defaults.update(overrides)
    return ClarificationAction(**defaults)


def _result_for(action, executor, **expected):
    result = executor.execute(action)
    for attr, value in expected.items():
        actual = getattr(result, attr)
        if actual != value:
            raise AssertionError(
                f"{attr}: 期望 {value!r}，实际 {actual!r}"
            )
    return result


class NoActionTests(unittest.TestCase):
    def setUp(self):
        self.executor = ClarificationExecutor(ReplyCoordinator())

    def test_no_action_leaves_coordinator_unchanged(self):
        action = _action()
        result = self.executor.execute(action)

        self.assertFalse(result.state_changed)
        self.assertEqual(result.action_type, ClarificationActionType.NO_ACTION)
        self.assertEqual(len(self.executor._coordinator.active_clarifications()), 0)

    def test_no_action_does_not_require_evidence_persistence(self):
        action = _action(requires_evidence_persistence=False)
        result = self.executor.execute(action)
        self.assertFalse(result.state_changed)

    def test_no_action_preserves_planner_reason_for_feedback(self):
        action = _action(reason="指定的问题编号不存在。")
        result = self.executor.execute(action)
        self.assertFalse(result.state_changed)
        self.assertEqual(result.reason, "指定的问题编号不存在。")


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.executor = ClarificationExecutor(ReplyCoordinator())

    def test_review_is_read_only(self):
        action = _action(
            action_type=ClarificationActionType.REVIEW,
            mutation_permission=ClarificationMutationPermission.READ_ONLY,
        )
        result = self.executor.execute(action)

        self.assertFalse(result.state_changed)
        self.assertIn("只读", result.reason)


class CreateTests(unittest.TestCase):
    def setUp(self):
        self.coordinator = ReplyCoordinator()
        self.executor = ClarificationExecutor(self.coordinator)

    def test_create_registers_new_question(self):
        action = _action(
            action_type=ClarificationActionType.CREATE,
            mutation_permission=ClarificationMutationPermission.PREPARE_CREATE,
            requires_evidence_persistence=True,
            question="加热到什么温度？需要加热多长时间？",
            missing_fields=("temperature", "duration"),
            requires_confirmation=False,
        )
        result = self.executor.execute(action)

        self.assertTrue(result.state_changed)
        self.assertEqual(result.affected_display_number, 1)
        self.assertIsNotNone(result.affected_clarification_id)
        self.assertIn("已创建待确认问题 1", result.reason)
        self.assertIn("加热到什么温度", result.reason)

        active = self.coordinator.active_clarifications()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].display_number, 1)
        self.assertEqual(active[0].missing_fields, ("temperature", "duration"))
        self.assertEqual(
            active[0].question,
            "加热到什么温度？需要加热多长时间？",
        )

    def test_create_increments_display_number(self):
        for i in range(3):
            action = _action(
                segment_id=i + 1,
                action_type=ClarificationActionType.CREATE,
                mutation_permission=ClarificationMutationPermission.PREPARE_CREATE,
                requires_evidence_persistence=True,
                question=f"问题 {i + 1}",
                missing_fields=("temperature",),
            )
            result = self.executor.execute(action)
            self.assertEqual(result.affected_display_number, i + 1)

    def test_create_with_confirmation_only(self):
        action = _action(
            action_type=ClarificationActionType.CREATE,
            mutation_permission=ClarificationMutationPermission.PREPARE_CREATE,
            requires_evidence_persistence=True,
            question="疑似ASR错词？",
            requires_confirmation=True,
        )
        result = self.executor.execute(action)

        self.assertTrue(result.state_changed)
        active = self.coordinator.active_clarifications()
        self.assertEqual(len(active), 1)
        self.assertTrue(active[0].requires_confirmation)

    def test_register_clarification_rejects_empty_question(self):
        with self.assertRaisesRegex(ValueError, "question"):
            self.coordinator.register_clarification(
                segment_id=1,
                raw_text="测试口述。",
                question="",
                missing_fields=("temperature",),
            )


class DeferTests(unittest.TestCase):
    def setUp(self):
        self.coordinator = ReplyCoordinator()
        self.executor = ClarificationExecutor(self.coordinator)
        self._register_and_pop("问题1", ("temperature",))

    def _register_and_pop(self, question, missing_fields):
        self.coordinator.register_clarification(
            segment_id=1,
            raw_text="测试口述。",
            question=question,
            missing_fields=missing_fields,
        )
        self.coordinator.pop_next_reply()

    def test_defer_changes_status(self):
        target = self.coordinator.current_clarification()
        action = _action(
            action_type=ClarificationActionType.DEFER,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision,
        )
        result = self.executor.execute(action)

        self.assertTrue(result.state_changed)
        self.assertIsNone(self.coordinator.current_clarification())
        active = self.coordinator.active_clarifications()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].status.value, "deferred")

    def test_defer_rejects_stale_revision(self):
        target = self.coordinator.current_clarification()
        action = _action(
            action_type=ClarificationActionType.DEFER,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision + 1,
        )
        result = self.executor.execute(action)

        self.assertFalse(result.state_changed)
        self.assertIn("版本已变更", result.reason)

    def test_defer_rejects_nonexistent_target(self):
        action = _action(
            action_type=ClarificationActionType.DEFER,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id="nonexistent",
            target_display_number=1,
            expected_revision=1,
        )
        result = self.executor.execute(action)

        self.assertFalse(result.state_changed)
        self.assertIn("未找到", result.reason)

    def test_defer_rejects_resolved_target(self):
        target = self.coordinator.current_clarification()
        self.coordinator.register_clarification(
            segment_id=2,
            raw_text="测试。",
            question="追问",
            missing_fields=("temperature",),
        )
        self.coordinator._apply_supplied_fields(
            {"temperature"}, segment_id=2, target_clarification_id=target.clarification_id
        )
        resolved = self.coordinator._find_clarification(target.clarification_id)

        action = _action(
            action_type=ClarificationActionType.DEFER,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=resolved.clarification_id,
            target_display_number=resolved.display_number,
            expected_revision=resolved.revision,
        )
        result = self.executor.execute(action)

        self.assertFalse(result.state_changed)


class ConfirmTests(unittest.TestCase):
    def setUp(self):
        self.coordinator = ReplyCoordinator()
        self.executor = ClarificationExecutor(self.coordinator)
        self.coordinator.register_clarification(
            segment_id=1,
            raw_text="测试口述。",
            question="疑似ASR错词？一液枪是移液枪吗？",
            requires_confirmation=True,
        )
        self.coordinator.pop_next_reply()

    def test_confirm_clears_requires_confirmation(self):
        target = self.coordinator.current_clarification()
        action = _action(
            action_type=ClarificationActionType.CONFIRM,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision,
            answer_text="是",
        )
        result = self.executor.execute(action)

        self.assertTrue(result.state_changed)
        updated = self.coordinator._find_clarification(target.clarification_id)
        self.assertFalse(updated.requires_confirmation)

    def test_confirm_fully_resolves_when_no_missing_fields(self):
        target = self.coordinator.current_clarification()
        action = _action(
            action_type=ClarificationActionType.CONFIRM,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision,
            answer_text="是的",
        )
        self.executor.execute(action)
        updated = self.coordinator._find_clarification(target.clarification_id)
        self.assertFalse(updated.is_unresolved)

    def test_confirm_rejects_stale_revision(self):
        target = self.coordinator.current_clarification()
        action = _action(
            action_type=ClarificationActionType.CONFIRM,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision + 1,
            answer_text="对",
        )
        result = self.executor.execute(action)

        self.assertFalse(result.state_changed)
        self.assertIn("版本已变更", result.reason)

    def test_confirm_rejects_non_confirmable_target(self):
        self.coordinator.register_clarification(
            segment_id=2,
            raw_text="测试。",
            question="不需要确认的问题",
            missing_fields=("temperature",),
        )
        target = self.coordinator._find_clarification("segment-2")

        action = _action(
            action_type=ClarificationActionType.CONFIRM,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision,
            answer_text="是的",
        )
        result = self.executor.execute(action)

        self.assertFalse(result.state_changed)
        self.assertIn("不需要确认", result.reason)

    def test_reject_suggestion_uses_same_transition_as_confirm(self):
        target = self.coordinator.current_clarification()
        action = _action(
            action_type=ClarificationActionType.REJECT_SUGGESTION,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision,
            answer_text="不是",
        )
        result = self.executor.execute(action)

        self.assertTrue(result.state_changed)
        updated = self.coordinator._find_clarification(target.clarification_id)
        self.assertFalse(updated.requires_confirmation)


class ConfirmWithEntitiesTests(unittest.TestCase):
    """确认/否定 + 补充实体：CONFIRM/REJECT 带 supplied_entity_fields 时填字段+确认。"""

    def setUp(self):
        self.coordinator = ReplyCoordinator()
        self.executor = ClarificationExecutor(self.coordinator)
        self.coordinator.register_clarification(
            segment_id=1,
            raw_text="测试口述。",
            question="疑似ASR错词？一液枪是移液枪吗？体积多少？",
            requires_confirmation=True,
            missing_fields=("amount_value", "amount_unit"),
        )
        self.coordinator.pop_next_reply()

    def _target(self):
        return self.coordinator.current_clarification()

    def test_confirm_with_all_entities_resolves(self):
        target = self._target()
        action = _action(
            action_type=ClarificationActionType.CONFIRM,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision,
            answer_text="是的，是移液枪，体积50毫升",
            supplied_entity_fields=("amount_value", "amount_unit"),
        )
        result = self.executor.execute(action)

        self.assertTrue(result.state_changed)
        self.assertTrue(result.resolved)
        updated = self.coordinator._find_clarification(target.clarification_id)
        self.assertFalse(updated.requires_confirmation)
        self.assertFalse(updated.is_unresolved)
        self.assertEqual(updated.missing_fields, ())

    def test_confirm_with_partial_entities_keeps_remaining(self):
        target = self._target()
        action = _action(
            action_type=ClarificationActionType.CONFIRM,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision,
            answer_text="是的，是移液枪",
            supplied_entity_fields=("amount_value",),
        )
        result = self.executor.execute(action)

        self.assertTrue(result.state_changed)
        self.assertFalse(result.resolved)
        self.assertEqual(result.remaining_fields, ("amount_unit",))
        updated = self.coordinator._find_clarification(target.clarification_id)
        self.assertFalse(updated.requires_confirmation)
        self.assertEqual(updated.missing_fields, ("amount_unit",))

    def test_reject_with_entities_fills_and_confirms(self):
        target = self._target()
        action = _action(
            action_type=ClarificationActionType.REJECT_SUGGESTION,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision,
            answer_text="不是，是移液枪，体积50毫升",
            supplied_entity_fields=("amount_value", "amount_unit"),
        )
        result = self.executor.execute(action)

        self.assertTrue(result.state_changed)
        self.assertTrue(result.resolved)
        updated = self.coordinator._find_clarification(target.clarification_id)
        self.assertFalse(updated.requires_confirmation)
        self.assertFalse(updated.is_unresolved)

    def test_confirm_extracts_entities_from_answer_text(self):
        # 确定性确认"是的，50微升"：无 supplied_entity_fields，靠执行器的
        # LLM 提取器从 answer_text 抽出实体，再填字段+确认。
        target = self._target()
        executor = ClarificationExecutor(
            self.coordinator,
            entity_extractor=FakeEntityExtractor({"amount_value", "amount_unit"}),
        )
        action = _action(
            action_type=ClarificationActionType.CONFIRM,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision,
            answer_text="是的50微升",
        )
        result = executor.execute(action)

        self.assertTrue(result.state_changed)
        self.assertTrue(result.resolved)
        updated = self.coordinator._find_clarification(target.clarification_id)
        self.assertFalse(updated.requires_confirmation)
        self.assertFalse(updated.is_unresolved)
        self.assertEqual(updated.missing_fields, ())


class AnswerTests(unittest.TestCase):
    def setUp(self):
        self.coordinator = ReplyCoordinator()
        self.executor = ClarificationExecutor(self.coordinator)
        self.coordinator.register_clarification(
            segment_id=1,
            raw_text="将溶液加热。",
            question="加热到什么温度？需要加热多长时间？",
            missing_fields=("temperature", "duration"),
        )
        self.coordinator.pop_next_reply()

    def test_answer_does_not_change_state(self):
        target = self.coordinator.current_clarification()
        action = _action(
            action_type=ClarificationActionType.ANSWER,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision,
            answer_text="60摄氏度加热10分钟",
        )
        result = self.executor.execute(action)

        self.assertFalse(result.state_changed)
        self.assertTrue(result.answer_text_received)
        self.assertIn("未配置实体提取器", result.reason)

    def test_answer_rejects_stale_revision(self):
        target = self.coordinator.current_clarification()
        action = _action(
            action_type=ClarificationActionType.ANSWER,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision + 1,
            answer_text="60摄氏度",
        )
        result = self.executor.execute(action)

        self.assertFalse(result.state_changed)
        self.assertIn("版本已变更", result.reason)

    def test_answer_rejects_nonexistent_target(self):
        action = _action(
            action_type=ClarificationActionType.ANSWER,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id="nonexistent",
            target_display_number=1,
            expected_revision=1,
            answer_text="60摄氏度",
        )
        result = self.executor.execute(action)

        self.assertFalse(result.state_changed)
        self.assertIn("未找到", result.reason)

    def test_answer_rejects_resolved_target(self):
        target = self.coordinator.current_clarification()
        self.coordinator._apply_supplied_fields(
            {"temperature", "duration"},
            segment_id=2,
            target_clarification_id=target.clarification_id,
        )
        resolved = self.coordinator._find_clarification(target.clarification_id)

        action = _action(
            action_type=ClarificationActionType.ANSWER,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=resolved.clarification_id,
            target_display_number=resolved.display_number,
            expected_revision=resolved.revision,
            answer_text="60摄氏度",
        )
        result = self.executor.execute(action)

        self.assertFalse(result.state_changed)

    def test_answer_with_extractor_fills_missing_fields(self):
        target = self.coordinator.current_clarification()
        extractor = FakeEntityExtractor({"temperature"})
        executor = ClarificationExecutor(
            self.coordinator,
            entity_extractor=extractor,
        )
        action = _action(
            action_type=ClarificationActionType.ANSWER,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision,
            answer_text="60摄氏度",
        )
        result = executor.execute(action)

        self.assertTrue(result.state_changed)
        self.assertTrue(result.answer_text_received)
        self.assertEqual(len(extractor.calls), 1)
        self.assertEqual(extractor.calls[0], "60摄氏度")

        updated = self.coordinator._find_clarification(target.clarification_id)
        self.assertEqual(updated.missing_fields, ("duration",))
        self.assertTrue(updated.is_unresolved)
        self.assertIn("仍需补充", result.reason)
        self.assertIn("duration", result.reason)
        self.assertEqual(result.remaining_fields, ("duration",))
        self.assertFalse(result.resolved)

    def test_answer_with_extractor_resolves_completely(self):
        target = self.coordinator.current_clarification()
        extractor = FakeEntityExtractor({"temperature", "duration"})
        executor = ClarificationExecutor(
            self.coordinator,
            entity_extractor=extractor,
        )
        action = _action(
            action_type=ClarificationActionType.ANSWER,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision,
            answer_text="60摄氏度加热10分钟",
        )
        result = executor.execute(action)

        self.assertTrue(result.state_changed)
        self.assertIn("问题已解决", result.reason)
        self.assertTrue(result.resolved)
        self.assertEqual(result.remaining_fields, ())

        updated = self.coordinator._find_clarification(target.clarification_id)
        self.assertFalse(updated.is_unresolved)

    def test_answer_with_extractor_empty_result_no_change(self):
        target = self.coordinator.current_clarification()
        extractor = FakeEntityExtractor(set())  # returns empty
        executor = ClarificationExecutor(
            self.coordinator,
            entity_extractor=extractor,
        )
        action = _action(
            action_type=ClarificationActionType.ANSWER,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision,
            answer_text="不知道",
        )
        result = executor.execute(action)

        self.assertFalse(result.state_changed)
        self.assertTrue(result.answer_text_received)
        self.assertIn("未从中提取到实体字段", result.reason)

    def test_answer_with_extractor_rejects_stale_revision(self):
        target = self.coordinator.current_clarification()
        extractor = FakeEntityExtractor({"temperature"})
        executor = ClarificationExecutor(
            self.coordinator,
            entity_extractor=extractor,
        )
        action = _action(
            action_type=ClarificationActionType.ANSWER,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision + 1,
            answer_text="60摄氏度",
        )
        result = executor.execute(action)

        self.assertFalse(result.state_changed)
        self.assertIn("版本已变更", result.reason)


class AnswerConfirmationPendingTests(unittest.TestCase):
    """字段已补齐但确认尚未完成时，反馈应为"仍需确认"而非"仍需补充：空"。"""

    def setUp(self):
        self.coordinator = ReplyCoordinator()
        self.executor = ClarificationExecutor(self.coordinator)
        self.coordinator.register_clarification(
            segment_id=1,
            raw_text="将缓冲液放入水域中加热。",
            question="请确认：您是指将缓冲液放入水浴中加热吗？另外，加热的目标温度和持续时间是多少？",
            missing_fields=("temperature", "duration"),
            requires_confirmation=True,
        )
        self.coordinator.pop_next_reply()

    def test_answer_filling_fields_but_pending_confirmation_says_need_confirm(self):
        target = self.coordinator.current_clarification()
        action = _action(
            action_type=ClarificationActionType.ANSWER,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision,
            answer_text="是的，60摄氏度10分钟",
            supplied_entity_fields=("temperature", "duration"),
        )
        result = self.executor.execute(action)

        self.assertTrue(result.state_changed)
        self.assertIn("仍需确认", result.reason)
        self.assertNotIn("仍需补充：", result.reason)
        self.assertFalse(result.resolved)
        self.assertEqual(result.remaining_fields, ())
        updated = self.coordinator._find_clarification(target.clarification_id)
        self.assertTrue(updated.is_unresolved)
        self.assertEqual(updated.missing_fields, ())



class ConfirmCompoundTests(unittest.TestCase):
    """同一句“确认 + 实体补充”必须原子地清确认标志并填字段。"""

    def setUp(self):
        self.coordinator = ReplyCoordinator()
        self.executor = ClarificationExecutor(self.coordinator)
        self.coordinator.register_clarification(
            segment_id=1,
            raw_text="一夜枪是移液枪吗？体积多少？",
            question="请确认：一夜枪是移液枪吗？另外体积是多少？",
            missing_fields=("amount_value", "amount_unit"),
            requires_confirmation=True,
        )
        self.coordinator.pop_next_reply()
        self.target = self.coordinator.current_clarification()

    def _confirm_action(self, **overrides):
        defaults = {
            "segment_id": 2,
            "action_type": ClarificationActionType.CONFIRM,
            "mutation_permission": ClarificationMutationPermission.PREPARE_UPDATE,
            "requires_evidence_persistence": True,
            "target_clarification_id": self.target.clarification_id,
            "target_display_number": self.target.display_number,
            "expected_revision": self.target.revision,
            "answer_text": "是的，体积为50毫升",
        }
        defaults.update(overrides)
        return _action(**defaults)

    def test_confirm_with_supplied_fields_fills_and_keeps_missing_remaining(self):
        result = self.executor.execute(
            self._confirm_action(
                supplied_entity_fields=("amount_value",)
            )
        )

        self.assertTrue(result.state_changed)
        self.assertIn("仍需补充", result.reason)
        self.assertEqual(result.remaining_fields, ("amount_unit",))
        self.assertFalse(result.resolved)

        updated = self.coordinator._find_clarification(
            self.target.clarification_id
        )
        self.assertFalse(updated.requires_confirmation)
        self.assertEqual(updated.missing_fields, ("amount_unit",))
        self.assertTrue(updated.is_unresolved)

    def test_confirm_with_all_supplied_fields_resolves(self):
        result = self.executor.execute(
            self._confirm_action(
                supplied_entity_fields=("amount_value", "amount_unit")
            )
        )

        self.assertTrue(result.state_changed)
        self.assertIn("问题已解决", result.reason)
        self.assertTrue(result.resolved)
        self.assertEqual(result.remaining_fields, ())

        updated = self.coordinator._find_clarification(
            self.target.clarification_id
        )
        self.assertFalse(updated.is_unresolved)
        self.assertEqual(updated.missing_fields, ())

    def test_confirm_uses_entity_extractor_for_plain_affirm_with_entities(self):
        extractor = FakeEntityExtractor({"amount_value", "amount_unit"})
        executor = ClarificationExecutor(
            self.coordinator,
            entity_extractor=extractor,
        )

        result = executor.execute(self._confirm_action())

        self.assertEqual(extractor.calls, ["是的，体积为50毫升"])
        self.assertTrue(result.state_changed)
        self.assertTrue(result.resolved)

        updated = self.coordinator._find_clarification(
            self.target.clarification_id
        )
        self.assertFalse(updated.is_unresolved)

    def test_pure_confirm_with_empty_extraction_keeps_missing_fields(self):
        extractor = FakeEntityExtractor(set())
        executor = ClarificationExecutor(
            self.coordinator,
            entity_extractor=extractor,
        )

        result = executor.execute(
            self._confirm_action(answer_text="是")
        )

        self.assertEqual(extractor.calls, ["是"])
        self.assertTrue(result.state_changed)
        self.assertFalse(result.resolved)
        self.assertEqual(
            result.remaining_fields,
            ("amount_value", "amount_unit"),
        )

        updated = self.coordinator._find_clarification(
            self.target.clarification_id
        )
        self.assertFalse(updated.requires_confirmation)
        self.assertEqual(
            updated.missing_fields,
            ("amount_value", "amount_unit"),
        )


class SafetyGateTests(unittest.TestCase):
    def setUp(self):
        self.executor = ClarificationExecutor(ReplyCoordinator())

    def test_state_changing_action_requires_evidence_persistence(self):
        for action_type in (
            ClarificationActionType.CREATE,
            ClarificationActionType.DEFER,
            ClarificationActionType.ANSWER,
            ClarificationActionType.CONFIRM,
            ClarificationActionType.REJECT_SUGGESTION,
        ):
            with self.subTest(action_type=action_type):
                kwargs = {
                    "action_type": action_type,
                    "requires_evidence_persistence": False,
                }
                update_types = {
                    ClarificationActionType.DEFER,
                    ClarificationActionType.ANSWER,
                    ClarificationActionType.CONFIRM,
                    ClarificationActionType.REJECT_SUGGESTION,
                }
                if action_type == ClarificationActionType.CREATE:
                    kwargs["mutation_permission"] = ClarificationMutationPermission.PREPARE_CREATE
                    kwargs["question"] = "测试问题"
                    kwargs["missing_fields"] = ("temperature",)
                elif action_type in update_types:
                    kwargs["mutation_permission"] = ClarificationMutationPermission.PREPARE_UPDATE
                    kwargs["target_clarification_id"] = "segment-1"
                    kwargs["target_display_number"] = 1
                    kwargs["expected_revision"] = 1
                    if action_type != ClarificationActionType.DEFER:
                        kwargs["answer_text"] = "答案"

                with self.assertRaises(ValueError):
                    _action(**kwargs)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.coordinator = ReplyCoordinator()
        self.executor = ClarificationExecutor(self.coordinator)

    def test_full_create_defer_confirm_lifecycle(self):
        # 1. CREATE
        create = _action(
            action_type=ClarificationActionType.CREATE,
            mutation_permission=ClarificationMutationPermission.PREPARE_CREATE,
            requires_evidence_persistence=True,
            question="加热到什么温度？需要加热多长时间？",
            missing_fields=("temperature", "duration"),
            requires_confirmation=True,
        )
        result = self.executor.execute(create)
        self.assertTrue(result.state_changed)
        self.assertEqual(self.coordinator._next_display_number, 2)

        # 2. 交付给用户
        reply = self.coordinator.pop_next_reply()
        self.assertIsNotNone(reply)

        target = self.coordinator.current_clarification()
        self.assertIsNotNone(target)
        self.assertEqual(target.display_number, 1)

        # 3. DEFER
        defer = _action(
            segment_id=2,
            action_type=ClarificationActionType.DEFER,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=target.clarification_id,
            target_display_number=target.display_number,
            expected_revision=target.revision,
        )
        result = self.executor.execute(defer)
        self.assertTrue(result.state_changed)
        self.assertIsNone(self.coordinator.current_clarification())

        # 4. reactivate
        self.coordinator.reactivate_question(display_number=1, segment_id=3)
        self.coordinator.pop_next_reply()
        reactivated = self.coordinator.current_clarification()
        self.assertTrue(reactivated.requires_confirmation)

        # 5. CONFIRM
        confirm = _action(
            segment_id=4,
            action_type=ClarificationActionType.CONFIRM,
            mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
            requires_evidence_persistence=True,
            target_clarification_id=reactivated.clarification_id,
            target_display_number=reactivated.display_number,
            expected_revision=reactivated.revision,
            answer_text="是",
        )
        result = self.executor.execute(confirm)
        self.assertTrue(result.state_changed)

        final = self.coordinator._find_clarification(reactivated.clarification_id)
        self.assertFalse(final.requires_confirmation)
        # 仍有 missing_fields，所以仍然 unresolved
        self.assertTrue(final.is_unresolved)
        self.assertEqual(final.missing_fields, ("temperature", "duration"))


class ExecutionResultTests(unittest.TestCase):
    def test_result_carries_full_identity(self):
        action = _action()
        executor = ClarificationExecutor(ReplyCoordinator())
        result = executor.execute(action)

        self.assertEqual(result.request_id, "req-1")
        self.assertEqual(result.session_id, "session-1")
        self.assertEqual(result.segment_id, 1)
        self.assertEqual(result.action_type, ClarificationActionType.NO_ACTION)
        self.assertIsInstance(result.reason, str)
        self.assertIsInstance(result.state_changed, bool)


if __name__ == "__main__":
    unittest.main()
