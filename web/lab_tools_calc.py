# -*- coding: utf-8 -*-
from __future__ import annotations

"""分子量/比例/溶液计算（由 lab_tools.py 拆分生成）。"""

import json
import re
import uuid
import threading
from datetime import datetime, timedelta
from pathlib import Path

from lab_tools_registry import (
    _REGISTRY, tool, PresentedToolResult, _attach_artifact,
    present_call, present_result,
    REPO_ROOT, RESULTS_DIR, STEP_IMPROVEMENTS_FILE,
    _timers, _timers_lock, _record_lock,
    domain, llm_bridge, settings_store,
    RecordCommand, SharedRecordService,
    generate_schedule, format_schedule_brief,
    get_remaining_schedule, format_remaining_brief,
    get_step_profile, get_next_passive_window,
    plan_multi_protocols, format_multi_protocol_brief,
    plan_clock_schedule,
    PresentationDeliveryPlan, build_delivery_plan,
    extract_entities,
    current_session_id, list_records, next_segment_id, save_record,
    save_protocol_preference, get_protocol_preference,
)

# ---------------- 分子量计算 ----------------

# 常用元素原子量（实验室常见范围，足够覆盖现有危化品/试剂库）
_ATOMIC_MASS = {
    "H": 1.008, "He": 4.003, "Li": 6.94, "Be": 9.012, "B": 10.81,
    "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998, "Ne": 20.180,
    "Na": 22.990, "Mg": 24.305, "Al": 26.982, "Si": 28.085, "P": 30.974,
    "S": 32.06, "Cl": 35.45, "Ar": 39.948, "K": 39.098, "Ca": 40.078,
    "Sc": 44.956, "Ti": 47.867, "V": 50.942, "Cr": 51.996, "Mn": 54.938,
    "Fe": 55.845, "Co": 58.933, "Ni": 58.693, "Cu": 63.546, "Zn": 65.38,
    "Ga": 69.723, "Ge": 72.630, "As": 74.922, "Se": 78.971, "Br": 79.904,
    "Kr": 83.798, "Rb": 85.468, "Sr": 87.62, "Y": 88.906, "Zr": 91.224,
    "Nb": 92.906, "Mo": 95.95, "Ru": 101.07, "Rh": 102.91, "Pd": 106.42,
    "Ag": 107.87, "Cd": 112.41, "In": 114.82, "Sn": 118.71, "Sb": 121.76,
    "Te": 127.60, "I": 126.90, "Xe": 131.29, "Cs": 132.91, "Ba": 137.33,
    "La": 138.91, "Ce": 140.12, "Pr": 140.91, "Nd": 144.24, "Sm": 150.36,
    "Eu": 151.96, "Gd": 157.25, "Tb": 158.93, "Dy": 162.50, "Ho": 164.93,
    "Er": 167.26, "Tm": 168.93, "Yb": 173.05, "Lu": 174.97, "Hf": 178.49,
    "Ta": 180.95, "W": 183.84, "Re": 186.21, "Os": 190.23, "Ir": 192.22,
    "Pt": 195.08, "Au": 196.97, "Hg": 200.59, "Tl": 204.38, "Pb": 207.2,
    "Bi": 208.98, "Th": 232.04, "U": 238.03,
}


def _parse_formula_unit(text: str):
    """递归解析一个化学式单元，支持括号和下标的任意组合。

    例如 H2O、NaCl、C6H12O6、CuSO4、(NH4)2SO4、Ca(OH)2、Al2(SO4)3。
    返回 (质量, 规范化显示, 结束下标)。
    """
    def parse(idx):
        mass = 0.0
        parts = []
        while idx < len(text):
            ch = text[idx]
            if ch == ")":
                return mass, "".join(parts), idx + 1
            if ch == "(":
                inner_mass, inner_disp, idx = parse(idx + 1)
                count = 0
                while idx < len(text) and text[idx].isdigit():
                    count = count * 10 + int(text[idx])
                    idx += 1
                n = count or 1
                mass += inner_mass * n
                parts.append(f"({inner_disp})" + (str(count) if count else ""))
                continue
            if ch.isupper():
                j = idx + 1
                if j < len(text) and text[j].islower():
                    j += 1
                element = text[idx:j]
                if element not in _ATOMIC_MASS:
                    raise ValueError(f"暂不支持元素：{element}")
                idx = j
                count = 0
                while idx < len(text) and text[idx].isdigit():
                    count = count * 10 + int(text[idx])
                    idx += 1
                n = count or 1
                mass += _ATOMIC_MASS[element] * n
                parts.append(f"{element}" + (str(count) if count else ""))
                continue
            raise ValueError(f"无法解析化学式：{text}")
        return mass, "".join(parts), idx

    mass, disp, idx = parse(0)
    if idx != len(text):
        raise ValueError(f"无法解析化学式：{text}")
    return mass, disp


def _parse_formula_custom(formula: str):
    """解析化学式，支持括号、下标和结晶水合物。

    支持：
    - 简单式：H2O、NaCl、C6H12O6、CuSO4
    - 括号：Ca(OH)2、(NH4)2SO4、Al2(SO4)3、KAl(SO4)2
    - 结晶水合物：CuSO4·5H2O、CuSO4.5H2O、Na2CO3·10H2O、FeSO4·7H2O
    - 复盐：KAl(SO4)2·12H2O
    """
    formula = str(formula or "").strip().replace(" ", "")
    if not formula:
        raise ValueError("化学式不能为空")
    formula = (formula.replace("·", ".")
               .replace("⋅", ".")
               .replace("∙", ".")
               .replace("×", ".")
               .replace("＊", ".")
               .replace("*", "."))
    if "." in formula:
        units = [u for u in formula.split(".") if u]
        total = 0.0
        displays = []
        for unit in units:
            coeff = 1
            body = unit
            match = re.match(r"^(\d+)(.*)$", unit)
            if match:
                coeff = int(match.group(1))
                body = match.group(2)
            mass, disp = _parse_formula_unit(body)
            total += coeff * mass
            displays.append((str(coeff) if coeff != 1 else "") + disp)
        return round(total, 3), "·".join(displays)
    mass, disp = _parse_formula_unit(formula)
    return round(mass, 3), disp


# 优先使用开源化学式库 molmass（BSD-3），缺失时回退到内置解析器。
try:
    from molmass import Formula as _MolFormula
except Exception:  # pragma: no cover - 依赖未安装时走内置解析器
    _MolFormula = None


def _parse_formula(formula: str):
    """解析化学式并计算分子量；优先用 molmass，失败回退内置解析器。"""
    if _MolFormula is not None:
        try:
            normalized = (str(formula or "").strip().replace(" ", "")
                          .replace("·", ".")
                          .replace("⋅", ".")
                          .replace("∙", ".")
                          .replace("×", ".")
                          .replace("＊", ".")
                          .replace("*", "."))
            mass = float(_MolFormula(normalized).mass)
            display = normalized
            try:
                _, display = _parse_formula_custom(formula)
            except Exception:
                pass
            return round(mass, 3), display
        except Exception:
            pass
    return _parse_formula_custom(formula)


_REAGENT_ALIASES = {
    "丙酮酸": {"name": "丙酮酸", "formula": "C3H4O3", "molecular_weight": "88.062", "name_en": "pyruvic acid"},
    "pyruvic acid": {"name": "丙酮酸", "formula": "C3H4O3", "molecular_weight": "88.062", "name_en": "pyruvic acid"},
    "丙酮酸钠": {"name": "丙酮酸钠", "formula": "C3H3NaO3", "molecular_weight": "110.04", "name_en": "sodium pyruvate"},
    "sodium pyruvate": {"name": "丙酮酸钠", "formula": "C3H3NaO3", "molecular_weight": "110.04", "name_en": "sodium pyruvate"},
    "乙酸钠": {"name": "乙酸钠", "formula": "C2H3NaO2", "molecular_weight": "82.03", "name_en": "sodium acetate"},
    "sodium acetate": {"name": "乙酸钠", "formula": "C2H3NaO2", "molecular_weight": "82.03", "name_en": "sodium acetate"},
}

@tool(
    "calculate_molecular_weight",
    "计算分子量或摩尔质量。用户问某试剂的分子量、摩尔质量、Mw、相对分子质量，"
    "或者给出化学式（如 H2O、NaCl、C6H12O6）要计算时调用。"
    "会先查试剂安全库，查不到就按化学式解析计算。",
    {
        "type": "object",
        "properties": {
            "reagent": {"type": "string", "description": "试剂中文名/英文名/化学式，如 氢氧化钠、NaCl、C6H12O6"}
        },
        "required": ["reagent"],
        "additionalProperties": False,
    },
    kind="read", title="分子量计算：{reagent}", experiment_command=True,
    present=lambda a, r: [
        (f"{r['name']}：{r['molecular_weight']}" if r.get("name") else f"{r['formula']}：{r['molecular_weight']}")
        + (" g/mol" if r.get("molecular_weight") else "")
    ],
)
def _calculate_molecular_weight(reagent):
    reagent = str(reagent or "").strip()
    if not reagent:
        raise ValueError("请输入试剂名称或化学式")
    from tools.reagent_catalog import find_reagent
    cat = find_reagent(reagent)
    if cat is not None and cat.get("molecular_weight"):
        return {
            "found": True,
            "name": cat.get("name_zh") or cat.get("name_en"),
            "formula": cat.get("formula"),
            "molecular_weight": float(cat["molecular_weight"]),
            "unit": "g/mol",
            "source": "通用试剂目录",
            "state": cat.get("state"),
            "density": cat.get("density"),
            "acidic": cat.get("acidic"),
            "pKa": cat.get("pKa"),
        }
    alias = _REAGENT_ALIASES.get(reagent.strip().lower()) or _REAGENT_ALIASES.get(reagent.strip())
    if alias is not None:
        return {
            "found": True,
            "name": alias["name"],
            "formula": alias["formula"],
            "molecular_weight": float(alias["molecular_weight"]),
            "unit": "g/mol",
            "source": "内置试剂别名表（经 PubChem 分子量复核）",
        }
    store = domain.hazmat()
    found = store.find(reagent) or (store.find_in_text(reagent) or [None])[0]
    if found is not None and found.molecular_weight:
        return {
            "found": True,
            "name": found.name_zh,
            "formula": found.molecular_formula,
            "molecular_weight": float(found.molecular_weight),
            "unit": "g/mol",
            "source": "试剂安全库（PubChem）",
        }
    if found is not None and found.molecular_formula:
        weight, formula = _parse_formula(found.molecular_formula)
        return {
            "found": True,
            "name": found.name_zh,
            "formula": formula,
            "molecular_weight": weight,
            "unit": "g/mol",
            "source": "按化学式从试剂安全库计算",
        }
    weight, formula = _parse_formula(reagent)
    return {
        "found": True,
        "name": None,
        "formula": formula,
        "molecular_weight": weight,
        "unit": "g/mol",
        "source": "按化学式解析计算",
    }


# ---------------- 比例换算计算 ----------------

@tool(
    "calculate_proportion",
    "按参考配方比例换算本次用量。用户给出参考用量、参考体积和本次目标体积时调用；"
    "只计算比例，不把参考值当成本次实际值。",
    {
        "type": "object",
        "properties": {
            "reference_quantity": {"type": "number", "description": "参考用量数值"},
            "reference_unit": {"type": "string", "description": "参考用量单位，如 g、mL"},
            "reference_volume": {"type": "number", "description": "参考配方体积"},
            "target_volume": {"type": "number", "description": "本次目标体积"},
            "volume_unit": {"type": "string", "enum": ["L", "mL"], "description": "参考体积和目标体积的单位"},
        },
        "required": ["reference_quantity", "reference_unit", "reference_volume", "target_volume"],
        "additionalProperties": False,
    },
    kind="read", title="比例换算：{reference_quantity}{reference_unit} → {target_volume}{volume_unit}", experiment_command=True,
    present=lambda a, r: [
        f"参考：{r['reference_quantity']} {r['reference_unit']} / {r['reference_volume']} {r['volume_unit']}",
        f"本次：{r['quantity']} {r['reference_unit']} / {r['target_volume']} {r['volume_unit']}",
        r["formula"],
    ],
)
def _calculate_proportion(reference_quantity, reference_unit, reference_volume, target_volume, volume_unit="mL"):
    quantity = float(reference_quantity)
    base_volume = float(reference_volume)
    requested_volume = float(target_volume)
    if quantity < 0 or base_volume <= 0 or requested_volume <= 0:
        raise ValueError("用量必须不小于 0，体积必须大于 0")
    unit = "L" if str(volume_unit or "mL").strip().lower() == "l" else "mL"
    scaled = quantity * requested_volume / base_volume
    return {
        "reference_quantity": quantity,
        "reference_unit": str(reference_unit or "").strip(),
        "reference_volume": base_volume,
        "target_volume": requested_volume,
        "volume_unit": unit,
        "quantity": round(scaled, 6),
        "formula": f"{quantity} × {requested_volume} ÷ {base_volume} = {round(scaled, 6)} {str(reference_unit or '').strip()}",
        "instruction": f"按比例计算，本次应取约 {round(scaled, 6)} {str(reference_unit or '').strip()}；这是计算值，实际以现场称量/测量为准。",
    }


# ---------------- 溶液配制与稀释计算 ----------------

@tool(
    "calculate_solution_prep",
    "计算配制一定摩尔浓度溶液所需的称样量。用户说“配 0.1 mol/L 的 NaOH 500 mL”"
    "“配 1 M Tris 100 mL”这类需求时调用。会先算分子量，再按 质量=浓度×体积×分子量 计算。",
    {
        "type": "object",
        "properties": {
            "reagent": {"type": "string", "description": "试剂中文名/英文名/化学式，如 氢氧化钠、NaCl、Tris"},
            "molarity": {"type": "number", "description": "目标浓度，单位 mol/L，如 0.1"},
            "volume": {"type": "number", "description": "目标体积数值"},
            "volume_unit": {"type": "string", "enum": ["L", "mL"], "description": "体积单位，默认 L"},
            "purity": {"type": "number", "description": "试剂纯度百分比，默认 100，如 98 表示 98%"},
        },
        "required": ["reagent", "molarity", "volume"],
        "additionalProperties": False,
    },
    kind="read", title="溶液配制：{molarity} mol/L {reagent} {volume}{volume_unit}", experiment_command=True,
    present=lambda a, r: [
        f"{r['name'] or r['formula']} 分子量 {r['molecular_weight']} g/mol",
        f"需称取 {r['mass_g']} g（{r['mass_mg']} mg）",
        r["instruction"],
    ],
)
def _calculate_solution_prep(reagent, molarity, volume, volume_unit="L", purity=100.0):
    mw_result = _calculate_molecular_weight(reagent)
    if not mw_result.get("molecular_weight"):
        raise ValueError("无法确定分子量，请提供正确的试剂名或化学式")
    molarity = float(molarity)
    if molarity <= 0:
        raise ValueError("浓度必须大于 0")
    volume = float(volume)
    if volume <= 0:
        raise ValueError("体积必须大于 0")
    raw_unit = str(volume_unit or "L").strip().lower()
    if raw_unit in ("ml", "毫升"):
        volume_l = volume / 1000.0
        unit_display = "mL"
    else:
        volume_l = volume
        unit_display = "L"
    purity = float(purity if purity is not None else 100)
    if purity <= 0 or purity > 100:
        raise ValueError("纯度应在 0-100 之间")
    mw = float(mw_result["molecular_weight"])
    mass_g = mw * molarity * volume_l / (purity / 100.0)
    return {
        "name": mw_result.get("name"),
        "formula": mw_result.get("formula"),
        "molecular_weight": mw,
        "molarity": molarity,
        "volume": volume,
        "volume_unit": unit_display,
        "purity": purity,
        "mass_g": round(mass_g, 4),
        "mass_mg": round(mass_g * 1000, 2),
        "instruction": f"称取约 {round(mass_g, 4)} g（{round(mass_g * 1000, 2)} mg），溶解后定容至 {volume} {unit_display}。",
    }


@tool(
    "calculate_dilution",
    "计算稀释需要的母液体积。用户说“把 1 M 母液稀释成 0.1 M 共 500 mL”时调用，"
    "使用 C1V1=C2V2。",
    {
        "type": "object",
        "properties": {
            "stock_concentration": {"type": "number", "description": "母液浓度，单位 mol/L 或 ×，如 1"},
            "final_concentration": {"type": "number", "description": "目标浓度，单位与母液一致，如 0.1"},
            "final_volume": {"type": "number", "description": "目标体积数值"},
            "volume_unit": {"type": "string", "enum": ["L", "mL"], "description": "体积单位，默认 mL"},
        },
        "required": ["stock_concentration", "final_concentration", "final_volume"],
        "additionalProperties": False,
    },
    kind="read", title="稀释计算：{final_concentration} 从 {stock_concentration} 配 {final_volume}{volume_unit}", experiment_command=True,
    present=lambda a, r: [
        f"取母液 {r['stock_volume']} {r['volume_unit']}",
        f"再加溶剂定容至 {r['final_volume']} {r['volume_unit']}",
    ],
)
def _calculate_dilution(stock_concentration, final_concentration, final_volume, volume_unit="mL"):
    c1 = float(stock_concentration)
    c2 = float(final_concentration)
    v2 = float(final_volume)
    if c1 <= 0 or c2 <= 0 or v2 <= 0:
        raise ValueError("浓度和体积必须大于 0")
    if c2 > c1:
        raise ValueError("目标浓度不能高于母液浓度")
    v1 = c2 * v2 / c1
    raw_unit = str(volume_unit or "mL").strip().lower()
    unit_display = "mL" if raw_unit in ("ml", "毫升") else "L"
    return {
        "stock_volume": round(v1, 4),
        "volume_unit": unit_display,
        "final_volume": v2,
        "formula": "C1V1=C2V2",
        "instruction": f"取母液 {round(v1, 4)} {unit_display}，再加溶剂定容至 {v2} {unit_display}。",
    }

