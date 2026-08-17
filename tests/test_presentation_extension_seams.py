# -*- coding: utf-8 -*-
"""PRESENT-EXTENSION-SEAMS-01：QUERY/DENY/WARNING/EXPORT 扩展接缝测试。"""

import unittest

from src.core.presentation_copy import copy_for_intent
from src.core.presentation_coordinator import (
    PresentationCoordinator,
)
from src.core.presentation_intent import (
    MessageKind,
    MessagePriority,
    PresentationIntent,
    ScreenTarget,
)
from src.core.presentation_projection import (
    DenyResultContract,
    ExportOutcome,
    QueryResultContract,
    WarningNotice,
    messages_for_deny_result,
    messages_for_export_result,
    messages_for_query_result,
    messages_for_warning,
)


def _intent(
    kind,
    args,
    priority=MessagePriority.ROUTINE,
    screen_target=ScreenTarget.STATUS,
):
    return PresentationIntent(
        intent_id="i-1",
        kind=kind,
        args=args,
        priority=priority,
        screen_target=screen_target,
    )


class QuerySeamTests(unittest.TestCase):
    def test_query_result_projects_semantic_args(self):
        intent = messages_for_query_result(
            QueryResultContract("试剂安全", "乙醇：易燃，远离火源。"),
            request_id="r1",
            source_segment_id=2,
        )[0]

        self.assertEqual(intent.kind, MessageKind.QUERY_RESULT)
        self.assertEqual(intent.args["title"], "试剂安全")
        self.assertEqual(intent.args["summary"], "乙醇：易燃，远离火源。")
        self.assertEqual(intent.source_segment_id, 2)
        self.assertEqual(intent.screen_target, ScreenTarget.DIALOGUE)

    def test_query_copy_renders_result(self):
        intent = _intent(
            MessageKind.QUERY_RESULT,
            {"title": "试剂安全", "summary": "乙醇：易燃，远离火源。"},
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertIn("查询结果：试剂安全", text)
        self.assertIn("乙醇：易燃，远离火源。", text)

    def test_query_contract_rejects_blank(self):
        with self.assertRaises(ValueError):
            QueryResultContract("", "summary")


class DenySeamTests(unittest.TestCase):
    def test_deny_result_projects_semantic_args(self):
        intent = messages_for_deny_result(
            DenyResultContract("该操作未被授权。"),
            request_id="r1",
        )[0]

        self.assertEqual(intent.kind, MessageKind.DENY_RESULT)
        self.assertEqual(intent.args["reason"], "该操作未被授权。")
        self.assertEqual(intent.priority, MessagePriority.DIRECT_ACK)

    def test_deny_copy_renders_reason(self):
        intent = _intent(
            MessageKind.DENY_RESULT,
            {"reason": "该操作未被授权。"},
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(text, "无法执行：该操作未被授权。")


class WarningSeamTests(unittest.TestCase):
    def test_warning_projects_critical_alert(self):
        intent = messages_for_warning(
            WarningNotice("乙醇易燃，请远离明火。"),
            request_id="r1",
        )[0]

        self.assertEqual(intent.kind, MessageKind.WARNING)
        self.assertEqual(intent.priority, MessagePriority.CRITICAL)
        self.assertEqual(intent.screen_target, ScreenTarget.ALERT)

    def test_warning_copy_renders_message(self):
        intent = _intent(
            MessageKind.WARNING,
            {"message": "乙醇易燃，请远离明火。"},
        )

        text = copy_for_intent(intent, ui_mode="user")

        self.assertEqual(text, "安全提醒：乙醇易燃，请远离明火。")

    def test_warning_v1_follows_fifo_and_does_not_reorder(self):
        coordinator = PresentationCoordinator()
        first = _intent(
            MessageKind.RECORD_ACK,
            {"result": "recorded", "step_number": 1},
        )
        warning = _intent(
            MessageKind.WARNING,
            {"message": "乙醇易燃。"},
            priority=MessagePriority.CRITICAL,
            screen_target=ScreenTarget.ALERT,
        )
        second = _intent(
            MessageKind.RECORD_ACK,
            {"result": "recorded", "step_number": 2},
        )

        coordinator.submit([first, warning, second])
        drained = coordinator.drain()

        self.assertEqual(
            [item.kind for item in drained],
            [MessageKind.RECORD_ACK, MessageKind.WARNING,
             MessageKind.RECORD_ACK],
        )


class ExportSeamTests(unittest.TestCase):
    def test_export_phases_project_and_render(self):
        cases = (
            ("started", None, "开始导出实验记录。"),
            ("succeeded", None, "实验记录导出成功。"),
            ("failed", "磁盘写入失败", "实验记录导出失败：磁盘写入失败。"),
        )
        for phase, detail, expected in cases:
            with self.subTest(phase=phase):
                intent = messages_for_export_result(
                    ExportOutcome(phase, detail),
                    request_id="r1",
                )[0]
                self.assertEqual(intent.kind, MessageKind.EXPORT_RESULT)
                self.assertEqual(intent.args["phase"], phase)

                text = copy_for_intent(intent, ui_mode="user")
                self.assertEqual(text, expected)

    def test_export_contract_rejects_unknown_phase(self):
        with self.assertRaises(ValueError):
            ExportOutcome("running")


if __name__ == "__main__":
    unittest.main()
