# -*- coding: utf-8 -*-
"""试剂识别与 Protocol 准备材料关联测试。"""

import sys
import unittest
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import domain  # noqa: E402


class ReagentRecognitionTests(unittest.TestCase):
    def test_analyze_reagents_finds_hazmat_and_reagent_prep(self):
        result = domain.analyze_reagents(
            ["加入氢氧化钠", "使用 50× TAE 电泳缓冲液"]
        )
        hazmat_names = {item["name"] for item in result["hazmat"]}
        prep_names = {item["name_zh"] for item in result["reagent_preps"]}
        self.assertIn("氢氧化钠", hazmat_names)
        self.assertIn("50× TAE 电泳缓冲液", prep_names)

    def test_protocol_prep_requirements_returns_items(self):
        result = domain.protocol_prep_requirements(
            "protocolsio-agarose-gel-instructor"
        )
        self.assertEqual(result["protocol_id"], "protocolsio-agarose-gel-instructor")
        self.assertGreaterEqual(len(result["items"]), 2)


if __name__ == "__main__":
    unittest.main()
