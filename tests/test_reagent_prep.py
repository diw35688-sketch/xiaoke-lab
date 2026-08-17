# -*- coding: utf-8 -*-
"""试剂配置数据合同测试。"""

import unittest

from src.core.reagent_prep import ReagentPrep, ReagentPrepError


def _prep(**overrides):
    data = {
        "reagent_prep_id": "tae-50x",
        "name_zh": "50× TAE 电泳缓冲液",
        "purpose": "琼脂糖凝胶电泳缓冲液母液",
        "target_concentration": "50×",
        "target_volume": "1 L",
        "solvent": "去离子水",
        "steps": ("称取 242 g Tris 碱", "加入 57.1 mL 冰醋酸"),
        "storage_condition": "室温",
        "expiry": "建议 6 个月内使用",
        "hazard_reagents": ("乙酸", "EDTA"),
        "source": "本科实验教学通用配方",
        "source_url": None,
        "review_status": "UNREVIEWED",
    }
    data.update(overrides)
    return ReagentPrep(**data)


class ReagentPrepContractTests(unittest.TestCase):
    def test_valid_prep_is_accepted_and_dict_round_trips(self):
        prep = _prep()
        self.assertEqual(prep.name_zh, "50× TAE 电泳缓冲液")
        self.assertEqual(prep.to_dict()["reagent_prep_id"], "tae-50x")

    def test_blank_id_is_rejected(self):
        with self.assertRaises(ReagentPrepError):
            _prep(reagent_prep_id="")

    def test_empty_steps_rejected(self):
        with self.assertRaises(ReagentPrepError):
            _prep(steps=())

    def test_blank_step_rejected(self):
        with self.assertRaises(ReagentPrepError):
            _prep(steps=("   ",))

    def test_duplicate_hazard_reagents_rejected(self):
        with self.assertRaises(ReagentPrepError):
            _prep(hazard_reagents=("乙酸", "乙酸"))

    def test_bad_review_status_rejected(self):
        with self.assertRaises(ReagentPrepError):
            _prep(review_status="PENDING")

    def test_from_dict_uses_unreviewed_default(self):
        prep = ReagentPrep.from_dict({
            "reagent_prep_id": "x",
            "name_zh": "X 溶液",
            "purpose": "测试",
            "steps": ["加入水"],
            "source": "测试来源",
        })
        self.assertEqual(prep.review_status, "UNREVIEWED")
        self.assertEqual(prep.hazard_reagents, ())


if __name__ == "__main__":
    unittest.main()
