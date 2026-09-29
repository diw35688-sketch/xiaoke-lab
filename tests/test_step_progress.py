# -*- coding: utf-8 -*-
"""web/step_progress.py 的确定性状态规则测试。

本模块只测纯逻辑（Fake 步骤对象），不访问文件、网络、数据库或大模型。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "web"))

from step_progress import (  # noqa: E402
    STATUS_COMPLETED,
    STATUS_ERROR,
    STATUS_WAITING,
    StepProgress,
    card_type_for,
)


def make_step(number, must_record):
    return SimpleNamespace(step_number=number, must_record=tuple(must_record))


class StepProgressTests(unittest.TestCase):
    def setUp(self):
        self.progress = StepProgress()

    def test_empty_must_record_waits_until_confirmed(self):
        # 没有现场必测项的步骤也不会自动完成——需要用户确认才打勾，
        # 否则一进来就被标记完成，体验上等于跳步。
        step = make_step(1, [])
        self.assertEqual(self.progress.status_for(step), STATUS_WAITING)
        self.progress.confirm(1)
        self.assertEqual(self.progress.status_for(step), STATUS_COMPLETED)

    def test_missing_fields_stay_waiting(self):
        step = make_step(2, ["amount_value", "temperature"])
        self.assertEqual(self.progress.status_for(step), STATUS_WAITING)
        self.progress.record(2, {"amount_value": "20"}, False)
        self.assertEqual(self.progress.status_for(step), STATUS_WAITING)

    def test_all_fields_recorded_completed(self):
        step = make_step(3, ["amount_value", "temperature"])
        self.progress.record(3, {"amount_value": "20", "temperature": "60"}, False)
        self.assertEqual(self.progress.status_for(step), STATUS_COMPLETED)

    def test_deviation_wins_over_completion(self):
        # 字段全齐但有偏差：必须处理，不能打勾。
        step = make_step(4, ["amount_value"])
        self.progress.record(4, {"amount_value": "30"}, True)
        self.assertEqual(self.progress.status_for(step), STATUS_ERROR)

    def test_record_ignores_falsy_values(self):
        step = make_step(5, ["amount_value"])
        self.progress.record(5, {"amount_value": None, "temperature": 0}, False)
        self.assertEqual(self.progress.status_for(step), STATUS_WAITING)

    def test_record_ignores_none_step_and_none_fields(self):
        # 自由模式没有步骤号，登记必须安全忽略，不抛异常。
        self.progress.record(None, {"amount_value": "20"}, False)
        step = make_step(6, ["amount_value"])
        self.progress.record(6, None, False)
        self.assertEqual(self.progress.status_for(step), STATUS_WAITING)

    def test_partial_then_complete_transition(self):
        step = make_step(7, ["a", "b"])
        self.progress.record(7, {"a": "1"}, False)
        self.assertEqual(self.progress.status_for(step), STATUS_WAITING)
        self.progress.record(7, {"b": "2"}, False)
        self.assertEqual(self.progress.status_for(step), STATUS_COMPLETED)

    def test_reset_clears_records_and_deviations(self):
        step = make_step(8, ["a"])
        self.progress.record(8, {"a": "1"}, True)
        self.assertEqual(self.progress.status_for(step), STATUS_ERROR)
        self.progress.reset()
        self.assertEqual(self.progress.status_for(step), STATUS_WAITING)

    def test_recorded_and_missing_lists(self):
        step = make_step(9, ["a", "b", "c"])
        self.progress.record(9, {"a": "1"}, False)
        self.assertEqual(self.progress.recorded_fields(9), ["a"])
        self.assertEqual(self.progress.missing_fields(step), ["b", "c"])
        self.progress.record(9, {"b": "2", "c": "3"}, False)
        self.assertEqual(self.progress.recorded_fields(9), ["a", "b", "c"])
        self.assertEqual(self.progress.missing_fields(step), [])

    def test_recorded_fields_empty_for_unknown_step(self):
        self.assertEqual(self.progress.recorded_fields(99), [])

    def test_missing_fields_excludes_non_must_fields(self):
        # 只有 must_record 里的字段才算"缺"；方案固定值(protocol_values)不参与。
        step = make_step(10, ["amount_value"])
        self.progress.record(10, {"temperature": "60"}, False)
        self.assertEqual(self.progress.missing_fields(step), ["amount_value"])
        self.assertEqual(self.progress.status_for(step), STATUS_WAITING)

    def test_restore_recovers_status(self):
        step = make_step(11, ["a", "b"])
        self.progress.restore(11, ["a", "b"], False)
        self.assertEqual(self.progress.status_for(step), STATUS_COMPLETED)
        self.assertEqual(self.progress.recorded_fields(11), ["a", "b"])

    def test_restore_with_deviation(self):
        step = make_step(12, ["a"])
        self.progress.restore(12, ["a"], True)
        self.assertEqual(self.progress.status_for(step), STATUS_ERROR)

    def test_restore_clears_previous_records(self):
        # 恢复是"整步覆盖"而非叠加：同一进度恢复两次不会重复累加。
        self.progress.record(13, {"a": "1", "b": "2"}, False)
        self.progress.restore(13, ["a"], False)
        self.assertEqual(self.progress.recorded_fields(13), ["a"])
        self.assertEqual(self.progress.status_for(make_step(13, ["a", "b"])), STATUS_WAITING)

    def test_restore_ignores_none_step(self):
        self.progress.restore(None, ["a"], True)   # 安全忽略，不抛异常
        self.assertEqual(self.progress.recorded_fields(1), [])

    def test_manual_confirm_completes_without_records(self):
        # 用户手动确认：必测字段没记齐也直接打勾，不再要求口述。
        step = make_step(14, ["a", "b"])
        self.assertEqual(self.progress.status_for(step), STATUS_WAITING)
        self.progress.confirm(14)
        self.assertEqual(self.progress.status_for(step), STATUS_COMPLETED)
        self.assertEqual(self.progress.missing_fields(step), [])

    def test_manual_confirm_clears_deviation(self):
        # 手动确认同时清除未处理偏差（人类责任确认）。
        step = make_step(15, ["a"])
        self.progress.record(15, {"a": "1"}, True)
        self.assertEqual(self.progress.status_for(step), STATUS_ERROR)
        self.progress.confirm(15)
        self.assertEqual(self.progress.status_for(step), STATUS_COMPLETED)

    def test_confirm_ignores_none_step(self):
        self.progress.confirm(None)   # 安全忽略，不抛异常
        self.assertEqual(self.progress.status_for(make_step(16, ["a"])), STATUS_WAITING)

    def test_reset_clears_confirmations(self):
        step = make_step(17, ["a"])
        self.progress.confirm(17)
        self.assertEqual(self.progress.status_for(step), STATUS_COMPLETED)
        self.progress.reset()
        self.assertEqual(self.progress.status_for(step), STATUS_WAITING)


class CardTypeMappingTests(unittest.TestCase):
    def test_error_status_maps_to_error_card(self):
        self.assertEqual(card_type_for(STATUS_ERROR, ["a"]), "error")

    def test_completed_maps_to_result_card(self):
        self.assertEqual(card_type_for(STATUS_COMPLETED, ["a"]), "result")

    def test_waiting_with_fields_maps_to_action(self):
        self.assertEqual(card_type_for(STATUS_WAITING, ["a"]), "action")

    def test_waiting_without_fields_maps_to_confirm(self):
        self.assertEqual(card_type_for(STATUS_WAITING, []), "confirm")


if __name__ == "__main__":
    unittest.main()
