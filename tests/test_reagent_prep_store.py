# -*- coding: utf-8 -*-
"""试剂配置库严格读取与写回测试。"""

import json
import tempfile
import unittest
from pathlib import Path

from src.core.reagent_prep import ReagentPrep, ReagentPrepError
from src.storage.reagent_prep_store import ReagentPrepStore


def _make_prep(prep_id="tae-50x"):
    return ReagentPrep(
        reagent_prep_id=prep_id,
        name_zh="50× TAE 电泳缓冲液",
        purpose="琼脂糖凝胶电泳缓冲液母液",
        target_concentration="50×",
        target_volume="1 L",
        solvent="去离子水",
        steps=("称取 242 g Tris 碱", "加入 57.1 mL 冰醋酸"),
        storage_condition="室温",
        expiry="建议 6 个月内使用",
        hazard_reagents=("乙酸",),
        source="本科实验教学通用配方",
        source_url=None,
        review_status="UNREVIEWED",
    )


def _write_library(path: Path, preps: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"schema_version": 1, "reagent_preps": [p.to_dict() for p in preps]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


class ReagentPrepStoreTests(unittest.TestCase):
    def test_loads_real_library(self):
        store = ReagentPrepStore()
        self.assertGreaterEqual(len(store.list_all()), 10)
        self.assertEqual(store.get_by_id("tae-50x").name_zh, "50× TAE 电泳缓冲液")

    def test_rejects_duplicate_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preps.json"
            _write_library(path, [_make_prep("a"), _make_prep("a")])
            with self.assertRaises(ReagentPrepError):
                ReagentPrepStore(path)

    def test_add_writes_new_prep(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preps.json"
            _write_library(path, [_make_prep("a")])
            store = ReagentPrepStore(path)
            store.add(_make_prep("b"))
            self.assertIsNotNone(store.get_by_id("b"))
            reloaded = ReagentPrepStore(path)
            self.assertIsNotNone(reloaded.get_by_id("b"))

    def test_add_rejects_existing_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preps.json"
            _write_library(path, [_make_prep("a")])
            store = ReagentPrepStore(path)
            with self.assertRaises(ReagentPrepError):
                store.add(_make_prep("a"))

    def test_add_many_all_or_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preps.json"
            _write_library(path, [_make_prep("a")])
            store = ReagentPrepStore(path)
            with self.assertRaises(ReagentPrepError):
                store.add_many([_make_prep("b"), _make_prep("a")])
            self.assertIsNone(store.get_by_id("b"))


if __name__ == "__main__":
    unittest.main()
