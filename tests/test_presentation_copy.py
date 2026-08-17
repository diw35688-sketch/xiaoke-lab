import unittest

from src.core.presentation_copy import (
    ConfirmationAckResult,
    ProgramStatus,
    RecordAckResult,
    ReviewItem,
    copy_for_intent,
)
from src.core.presentation_intent import (
    MessageKind,
    MessagePriority,
    PresentationIntent,
    ScreenTarget,
)


def _make_intent(kind, *, args, source_segment_id=4, screen_target=None):
    return PresentationIntent(
        intent_id="i-1",
        kind=kind,
        args=args,
        priority=MessagePriority.ROUTINE,
        screen_target=screen_target or ScreenTarget.STATUS,
        source_segment_id=source_segment_id,
    )


class ProgramFeedbackCopyTests(unittest.TestCase):
    def test_program_statuses_use_fixed_user_copy(self):
        expected = {
            ProgramStatus.STARTING: "实验语音智能体正在启动，请稍候。",
            ProgramStatus.READY: (
                "实验语音智能体已就绪，正在等待唤醒。"
                "按 Ctrl+C 可以退出程序。"
            ),
            ProgramStatus.WAITING: (
                "已返回待机。可以再次说“小科小科”开始新会话；"
                "按 Ctrl+C 退出程序。"
            ),
            ProgramStatus.EXITED: "已退出实验语音智能体。",
        }

        for status, expected_text in expected.items():
            with self.subTest(status=status):
                text = copy_for_intent(
                    _make_intent(
                        MessageKind.PROGRAM_STATUS,
                        args={"status": status},
                    ),
                    ui_mode="user",
                )
                self.assertEqual(text, expected_text)

    def test_wake_ack_uses_keyword_contract(self):
        text = copy_for_intent(
            _make_intent(
                MessageKind.WAKE_ACK,
                args={"keyword": " 小科小科 "},
            ),
            ui_mode="user",
        )

        self.assertEqual(text, "唤醒成功：小科小科")

    def test_program_feedback_rejects_missing_or_unknown_args(self):
        with self.assertRaises(ValueError):
            copy_for_intent(
                _make_intent(MessageKind.PROGRAM_STATUS, args={}),
                ui_mode="user",
            )
        with self.assertRaises(ValueError):
            copy_for_intent(
                _make_intent(
                    MessageKind.PROGRAM_STATUS,
                    args={"status": "unknown"},
                ),
                ui_mode="user",
            )
        with self.assertRaises(ValueError):
            copy_for_intent(
                _make_intent(MessageKind.WAKE_ACK, args={"keyword": " "}),
                ui_mode="user",
            )


class RecordAckCopyTests(unittest.TestCase):
    def test_user_copy_for_recorded_step(self):
        intent = _make_intent(
            MessageKind.RECORD_ACK,
            args={"result": RecordAckResult.RECORDED, "step_number": 3},
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(text, "已记录实验步骤 3。")

    def test_admin_copy_includes_internal_source_reference(self):
        intent = _make_intent(
            MessageKind.RECORD_ACK,
            args={"result": RecordAckResult.RECORDED, "step_number": 3},
        )

        text = copy_for_intent(intent, ui_mode="admin")

        self.assertEqual(text, "已记录实验步骤 3（来源口述 4）。")

    def test_degraded_copy_uses_plain_language(self):
        intent = _make_intent(
            MessageKind.RECORD_ACK,
            args={"result": RecordAckResult.DEGRADED},
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(text, "原始记录已保存，结构化处理暂时不可用。")

    def test_failed_copy_confirms_that_raw_record_was_saved(self):
        intent = _make_intent(
            MessageKind.RECORD_ACK,
            args={"result": RecordAckResult.FAILED},
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(text, "本段结构化处理失败，原始记录已保存。")

    def test_confirmed_with_remaining_fields_lists_missing(self):
        intent = _make_intent(
            MessageKind.CONFIRMATION_ACK,
            args={
                "result": ConfirmationAckResult.CONFIRMED,
                "display_number": 2,
                "remaining_fields": ("duration",),
            },
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(text, "已确认问题 2，仍需补充：时间。")

    def test_confirmed_resolved_uses_compound_copy(self):
        intent = _make_intent(
            MessageKind.CONFIRMATION_ACK,
            args={
                "result": ConfirmationAckResult.CONFIRMED,
                "display_number": 2,
                "resolved": True,
            },
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(text, "已确认并补充问题 2，问题已解决。")

    def test_missing_result_is_rejected(self):
        intent = _make_intent(
            MessageKind.RECORD_ACK,
            args={},
        )

        with self.assertRaises(ValueError):
            copy_for_intent(intent, ui_mode="user")

    def test_unknown_result_is_rejected(self):
        intent = _make_intent(
            MessageKind.RECORD_ACK,
            args={"result": "unknown"},
        )

        with self.assertRaises(ValueError):
            copy_for_intent(intent, ui_mode="user")

    def test_recorded_step_requires_positive_integer(self):
        intent = _make_intent(
            MessageKind.RECORD_ACK,
            args={"result": RecordAckResult.RECORDED, "step_number": 0},
        )

        with self.assertRaises(ValueError):
            copy_for_intent(intent, ui_mode="user")

    def test_unknown_ui_mode_is_rejected(self):
        intent = _make_intent(
            MessageKind.RECORD_ACK,
            args={"result": RecordAckResult.DEGRADED},
        )

        with self.assertRaises(ValueError):
            copy_for_intent(intent, ui_mode="developer")

    def test_unsupported_message_kind_is_rejected(self):
        intent = _make_intent(
            MessageKind.SAFETY_ALERT,
            args={},
        )

        with self.assertRaises(ValueError):
            copy_for_intent(intent, ui_mode="user")


class ClarificationCopyTests(unittest.TestCase):
    def test_question_stands_alone_without_dev_prefix(self):
        intent = _make_intent(
            MessageKind.CLARIFICATION,
            args={"question": "第2步需要离心多长时间？"},
            screen_target=ScreenTarget.CURRENT_QUESTION,
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(text, "小科：第2步需要离心多长时间？")

    def test_admin_appends_source_without_double_punctuation(self):
        intent = _make_intent(
            MessageKind.CLARIFICATION,
            args={"question": "第2步需要离心多长时间？"},
            screen_target=ScreenTarget.CURRENT_QUESTION,
        )

        text = copy_for_intent(intent, ui_mode="admin")

        self.assertEqual(text, "小科：第2步需要离心多长时间？（来源口述 4）")

    def test_missing_question_is_rejected(self):
        intent = _make_intent(
            MessageKind.CLARIFICATION,
            args={},
            screen_target=ScreenTarget.CURRENT_QUESTION,
        )

        with self.assertRaises(ValueError):
            copy_for_intent(intent, ui_mode="user")

    def test_blank_question_is_rejected(self):
        intent = _make_intent(
            MessageKind.CLARIFICATION,
            args={"question": "  "},
            screen_target=ScreenTarget.CURRENT_QUESTION,
        )

        with self.assertRaises(ValueError):
            copy_for_intent(intent, ui_mode="user")


class ConfirmationAckCopyTests(unittest.TestCase):
    def test_answered_with_remaining_fields_translates_field_names(self):
        intent = _make_intent(
            MessageKind.CONFIRMATION_ACK,
            args={
                "result": ConfirmationAckResult.ANSWERED,
                "display_number": 1,
                "remaining_fields": ("temperature", "duration"),
            },
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(text, "已补充问题 1，仍需补充：温度、时间。")

    def test_answered_resolved_uses_plain_ack(self):
        intent = _make_intent(
            MessageKind.CONFIRMATION_ACK,
            args={
                "result": ConfirmationAckResult.ANSWERED,
                "display_number": 1,
                "resolved": True,
            },
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(text, "已补充问题 1，问题已解决。")

    def test_answered_without_fields_needs_confirmation(self):
        intent = _make_intent(
            MessageKind.CONFIRMATION_ACK,
            args={
                "result": ConfirmationAckResult.ANSWERED,
                "display_number": 1,
            },
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(text, "已补充问题 1，仍需确认。")

    def test_confirmed_uses_plain_ack(self):
        intent = _make_intent(
            MessageKind.CONFIRMATION_ACK,
            args={
                "result": ConfirmationAckResult.CONFIRMED,
                "display_number": 2,
            },
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(text, "已确认问题 2。")

    def test_missing_result_is_rejected(self):
        intent = _make_intent(
            MessageKind.CONFIRMATION_ACK,
            args={"display_number": 1},
        )

        with self.assertRaises(ValueError):
            copy_for_intent(intent, ui_mode="user")

    def test_unknown_result_is_rejected(self):
        intent = _make_intent(
            MessageKind.CONFIRMATION_ACK,
            args={"result": "deferred", "display_number": 1},
        )

        with self.assertRaises(ValueError):
            copy_for_intent(intent, ui_mode="user")

    def test_missing_display_number_is_rejected(self):
        intent = _make_intent(
            MessageKind.CONFIRMATION_ACK,
            args={"result": ConfirmationAckResult.CONFIRMED},
        )

        with self.assertRaises(ValueError):
            copy_for_intent(intent, ui_mode="user")

    def test_non_positive_display_number_is_rejected(self):
        intent = _make_intent(
            MessageKind.CONFIRMATION_ACK,
            args={
                "result": ConfirmationAckResult.CONFIRMED,
                "display_number": 0,
            },
        )

        with self.assertRaises(ValueError):
            copy_for_intent(intent, ui_mode="user")

    def test_answered_requires_bool_resolved(self):
        intent = _make_intent(
            MessageKind.CONFIRMATION_ACK,
            args={
                "result": ConfirmationAckResult.ANSWERED,
                "display_number": 1,
                "resolved": "yes",
            },
        )

        with self.assertRaises(ValueError):
            copy_for_intent(intent, ui_mode="user")

    def test_answered_requires_tuple_remaining_fields(self):
        intent = _make_intent(
            MessageKind.CONFIRMATION_ACK,
            args={
                "result": ConfirmationAckResult.ANSWERED,
                "display_number": 1,
                "remaining_fields": ["temperature"],
            },
        )

        with self.assertRaises(ValueError):
            copy_for_intent(intent, ui_mode="user")


class NoActionFeedbackCopyTests(unittest.TestCase):
    def test_missing_number_guides_to_review(self):
        intent = _make_intent(
            MessageKind.NO_ACTION_FEEDBACK,
            args={"reason": "指定的问题编号不存在。"},
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(
            text,
            "没有找到你指定的问题编号，请先查看当前待确认问题。",
        )

    def test_missing_answer_guides_targeted_answer(self):
        intent = _make_intent(
            MessageKind.NO_ACTION_FEEDBACK,
            args={"reason": "指定问题答复缺少答案内容。"},
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(
            text,
            "请说明要回答的内容，例如“问题1，50毫升”。",
        )

    def test_no_current_target_feedback(self):
        intent = _make_intent(
            MessageKind.NO_ACTION_FEEDBACK,
            args={"reason": "当前没有可确认或否定的ACTIVE建议。"},
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(
            text,
            "当前没有可以执行这个操作的问题。",
        )

    def test_abstention_feedback(self):
        intent = _make_intent(
            MessageKind.NO_ACTION_FEEDBACK,
            args={"reason": "风险策略明确弃权，不能根据模型候选修改待确认状态。"},
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(
            text,
            "我听到了，但没把握安全地执行，请换个说法试试。",
        )

    def test_unknown_reason_uses_fallback(self):
        intent = _make_intent(
            MessageKind.NO_ACTION_FEEDBACK,
            args={"reason": "未知原因。"},
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(
            text,
            "我听到了，但暂时无法处理这句话。",
        )


class DeferredCopyTests(unittest.TestCase):
    def test_deferred_uses_plain_ack(self):
        intent = _make_intent(
            MessageKind.CLARIFICATION_DEFERRED,
            args={"display_number": 3},
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(text, "问题 3 已暂缓。")


class ReviewCopyTests(unittest.TestCase):
    def test_empty_review_uses_plain_language(self):
        intent = _make_intent(
            MessageKind.CLARIFICATION_REVIEW,
            args={"items": ()},
            screen_target=ScreenTarget.DIALOGUE,
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(text, "当前没有待确认问题。")

    def test_review_lists_items_with_status(self):
        intent = _make_intent(
            MessageKind.CLARIFICATION_REVIEW,
            args={
                "items": (
                    ReviewItem(
                        display_number=1,
                        is_deferred=False,
                        question="离心多长时间？",
                    ),
                    ReviewItem(
                        display_number=2,
                        is_deferred=True,
                        question="温度是多少？",
                    ),
                ),
            },
            screen_target=ScreenTarget.DIALOGUE,
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(
            text,
            "当前共有 2 个待确认问题：\n"
            "- 问题 1（待回答）：离心多长时间？\n"
            "- 问题 2（已暂缓）：温度是多少？",
        )

    def test_review_rejects_non_tuple_items(self):
        intent = _make_intent(
            MessageKind.CLARIFICATION_REVIEW,
            args={"items": [ReviewItem(1, False, "q")]},
        )

        with self.assertRaises(ValueError):
            copy_for_intent(intent, ui_mode="user")

    def test_review_rejects_non_review_item(self):
        intent = _make_intent(
            MessageKind.CLARIFICATION_REVIEW,
            args={"items": ("not-a-review-item",)},
        )

        with self.assertRaises(ValueError):
            copy_for_intent(intent, ui_mode="user")

    def test_review_item_rejects_non_positive_number(self):
        with self.assertRaises(ValueError):
            ReviewItem(display_number=0, is_deferred=False, question="q")


class PassthroughCopyTests(unittest.TestCase):
    def test_stage_summary_passthrough_text(self):
        intent = _make_intent(
            MessageKind.STAGE_SUMMARY,
            args={"text": "系统将立即继续监听。"},
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(text, "系统将立即继续监听。")

    def test_transcript_passthrough_text(self):
        intent = _make_intent(
            MessageKind.TRANSCRIPT,
            args={"text": "本段 ASR 识别完成：加入缓冲液"},
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(text, "本段 ASR 识别完成：加入缓冲液")

    def test_passthrough_requires_text(self):
        intent = _make_intent(
            MessageKind.TRANSCRIPT,
            args={},
        )

        with self.assertRaises(ValueError):
            copy_for_intent(intent, ui_mode="user")


class SessionClosingSummaryCopyTests(unittest.TestCase):
    def test_summary_explicitly_reports_no_pending_questions(self):
        intent = _make_intent(
            MessageKind.SESSION_CLOSING_SUMMARY,
            args={
                "experiment_step_count": 2,
                "pending_items": (),
            },
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(
            text,
            "实验记录会话已结束。\n"
            "本次共记录 2 个实验步骤。\n"
            "没有待确认问题。",
        )

    def test_summary_includes_pending_question_details(self):
        intent = _make_intent(
            MessageKind.SESSION_CLOSING_SUMMARY,
            args={
                "experiment_step_count": 1,
                "pending_items": (
                    ReviewItem(1, False, "加热多长时间？"),
                    ReviewItem(2, True, "温度是多少？"),
                ),
            },
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(text.count("会话已结束"), 1)
        self.assertIn("仍有 2 个待确认问题", text)
        self.assertIn("问题 1（待回答）：加热多长时间？", text)
        self.assertIn("问题 2（已暂缓）：温度是多少？", text)

    def test_summary_rejects_invalid_contract(self):
        with self.assertRaises(ValueError):
            copy_for_intent(
                _make_intent(
                    MessageKind.SESSION_CLOSING_SUMMARY,
                    args={"experiment_step_count": -1, "pending_items": ()},
                ),
                ui_mode="user",
            )

        with self.assertRaises(ValueError):
            copy_for_intent(
                _make_intent(
                    MessageKind.SESSION_CLOSING_SUMMARY,
                    args={"experiment_step_count": 0, "pending_items": []},
                ),
                ui_mode="user",
            )


if __name__ == "__main__":
    unittest.main()
