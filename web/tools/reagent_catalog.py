# -*- coding: utf-8 -*-
"""通用试剂属性目录：名称/同义词/CAS/分子式/分子量/物态/密度/酸碱性。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from config import BASE_DIR

CATALOG_FILE = BASE_DIR.parent / "data" / "reagents" / "reagent_catalog.json"


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, dict]:
    raw = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    entries = raw.get("reagents", [])
    by_alias: dict[str, dict] = {}
    for item in entries:
        names = [item.get("name_zh", ""), item.get("name_en", "")]
        names.extend(item.get("synonyms", []) or [])
        for name in names:
            if name:
                by_alias[str(name).strip().lower()] = item
                by_alias[str(name).strip()] = item
    return by_alias


def find_reagent(name: str) -> dict | None:
    if not name:
        return None
    key = str(name).strip()
    catalog = load_catalog()
    return catalog.get(key.lower()) or catalog.get(key)
