# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web"))

import lab_tools


def handler():
    return lab_tools._REGISTRY["calculate_molecular_weight"]["handler"]


def test_lookup_reagent_by_name():
    result = handler()("氢氧化钠")
    assert result["found"] is True
    assert result["name"] == "氢氧化钠"
    assert abs(result["molecular_weight"] - 39.997) < 0.01


def test_lookup_reagent_by_formula():
    result = handler()("NaCl")
    assert result["found"] is True
    assert result["formula"] == "NaCl"
    assert abs(result["molecular_weight"] - 58.44) < 0.01


def test_parse_organic_formula():
    result = handler()("C6H12O6")
    assert result["found"] is True
    assert result["formula"] == "C6H12O6"
    assert abs(result["molecular_weight"] - 180.156) < 0.05


def test_parse_hydrated_salt():
    result = handler()("CuSO4")
    assert result["found"] is True
    assert abs(result["molecular_weight"] - 159.61) < 0.05


def test_parse_copper_sulfate_pentahydrate_formula():
    result = handler()("CuSO4·5H2O")
    assert result["found"] is True
    assert result["formula"] == "CuSO4·5H2O"
    assert abs(result["molecular_weight"] - 249.69) < 0.05


def test_parse_dot_separated_hydrate():
    result = handler()("FeSO4.7H2O")
    assert result["found"] is True
    assert result["formula"] == "FeSO4·7H2O"
    assert abs(result["molecular_weight"] - 278.01) < 0.05


def test_lookup_chinese_hydrate_name():
    result = handler()("五水硫酸铜")
    assert result["found"] is True
    assert result["name"] == "五水硫酸铜"
    assert abs(result["molecular_weight"] - 249.69) < 0.01
