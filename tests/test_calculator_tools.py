# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web"))

import lab_tools


def solution_handler():
    return lab_tools._REGISTRY["calculate_solution_prep"]["handler"]


def dilution_handler():
    return lab_tools._REGISTRY["calculate_dilution"]["handler"]


def test_solution_prep_naoh_1m_100ml():
    result = solution_handler()("NaOH", 1, 100, "mL", 100)
    # molmass 库对 NaOH 的分子量为 40.0（Na 22.99 + O 16.00 + H 1.01 ≈ 40.0）
    assert abs(result["molecular_weight"] - 40.0) < 0.01
    assert abs(result["mass_g"] - 4.0) < 0.01
    assert result["volume_unit"] == "mL"


def test_solution_prep_purity_correction():
    result = solution_handler()("NaCl", 0.5, 1, "L", 98)
    # 0.5 mol * 58.44 g/mol / 0.98 = 29.8163 g
    assert abs(result["mass_g"] - 29.8163) < 0.01


def test_dilution_c1v1_c2v2():
    result = dilution_handler()(1, 0.1, 500, "mL")
    assert abs(result["stock_volume"] - 50.0) < 0.001
    assert result["volume_unit"] == "mL"
