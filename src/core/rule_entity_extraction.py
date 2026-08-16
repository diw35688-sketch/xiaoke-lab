# -*- coding: utf-8 -*-
"""不依赖大模型的规则实体抽取。

用途：模型未配置、网络故障或调用失败时，仍然从口述里抽出**可确定的**事实
（数量、单位、浓度、温度、时长、试剂名），而不是整段退回原文。

边界（有意为之）：
- 只抽取有明确书写形式的量值，不做语义理解、不猜测意图。
- 抽不到就留空，绝不编造；宁可少抽，不可抽错。
- 这是降级路径，不是替代大模型；模型可用时以模型结果为准。
"""

from __future__ import annotations

import re

from src.llm.schemas import ExperimentEntities

# 中文数字转换，覆盖口述里常见的写法
_CN_DIGITS = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}

_UNIT_PATTERN = (
    r"(毫升|微升|升|毫克|微克|千克|克|摩尔每升|摩尔|毫摩尔|"
    r"纳米|毫米|厘米|米|摄氏度|度|分钟|小时|秒|转|次|滴|"
    r"mL|ml|µL|uL|L|mg|µg|ug|kg|g|nm|mm|cm|mol/L|mmol/L|rpm|min|sec|h|℃)"
)

_ACTIONS = (
    "称取", "称量", "加入", "移取", "溶解", "稀释", "定容", "混匀", "搅拌",
    "加热", "冷却", "滴定", "润洗", "调节", "测量", "测定", "观察", "记录",
    "离心", "过滤", "静置", "孵育", "洗涤", "转移", "配制", "调零", "预热",
)


def _cn_number(text: str) -> str | None:
    """把常见中文数字转成阿拉伯数字；无法确定时返回 None。"""
    if not text:
        return None
    if text.isdigit():
        return text
    total = 0
    if "十" in text:
        left, _, right = text.partition("十")
        tens = _CN_DIGITS.get(left, 1 if left == "" else None)
        ones = _CN_DIGITS.get(right, 0 if right == "" else None)
        if tens is None or ones is None:
            return None
        total = tens * 10 + ones
        return str(total)
    if len(text) == 1 and text in _CN_DIGITS:
        return str(_CN_DIGITS[text])
    return None


def extract_entities(transcript: str, known_terms: tuple[str, ...] = ()) -> ExperimentEntities:
    """从口述文本抽取可确定的实体；抽不到的字段保持 None。"""
    if not isinstance(transcript, str) or not transcript.strip():
        return ExperimentEntities()

    text = transcript.strip()
    fields: dict[str, str] = {}

    # 动作：命中已知动词表才登记，不做泛化猜测
    for action in _ACTIONS:
        if action in text:
            fields["action"] = action
            break

    # 数量 + 单位：阿拉伯数字或中文数字
    match = re.search(r"(\d+(?:\.\d+)?)\s*" + _UNIT_PATTERN, text)
    if not match:
        cn = re.search(r"([零一二两三四五六七八九十]+)\s*" + _UNIT_PATTERN, text)
        if cn:
            value = _cn_number(cn.group(1))
            if value:
                match = None
                fields["amount_value"] = value
                fields["amount_unit"] = cn.group(2)
    if match:
        fields["amount_value"] = match.group(1)
        fields["amount_unit"] = match.group(2)

    # 浓度：带 mol/L 或“摩尔每升”的量值单独归到 concentration
    concentration = re.search(
        r"(\d+(?:\.\d+)?)\s*(mol/L|mmol/L|摩尔每升|毫摩尔每升|%|％)", text
    )
    if concentration:
        fields["concentration"] = concentration.group(1) + concentration.group(2)
        if fields.get("amount_unit") in {"mol/L", "mmol/L", "摩尔每升", "%", "％"}:
            fields.pop("amount_value", None)
            fields.pop("amount_unit", None)

    # 温度：阿拉伯数字或中文数字
    temperature = re.search(r"(\d+(?:\.\d+)?)\s*(摄氏度|℃|度)", text)
    if temperature:
        fields["temperature"] = temperature.group(1) + temperature.group(2)
    else:
        cn_temp = re.search(r"([零一二两三四五六七八九十]+)\s*(摄氏度|℃|度)", text)
        if cn_temp:
            value = _cn_number(cn_temp.group(1))
            if value:
                fields["temperature"] = value + cn_temp.group(2)
    # 温度单位不应重复占用通用数量字段
    if "temperature" in fields and fields.get("amount_unit") in {"摄氏度", "℃", "度"}:
        fields.pop("amount_value", None)
        fields.pop("amount_unit", None)
        if fields.get("amount_unit") in {"摄氏度", "℃", "度"}:
            fields.pop("amount_value", None)
            fields.pop("amount_unit", None)

    # 时长
    duration = re.search(r"(\d+(?:\.\d+)?)\s*(分钟|小时|秒|min|sec|h)", text)
    if not duration:
        cn_duration = re.search(r"([零一二两三四五六七八九十]+)\s*(分钟|小时|秒)", text)
        if cn_duration:
            value = _cn_number(cn_duration.group(1))
            if value:
                fields["duration"] = value + cn_duration.group(2)
    else:
        fields["duration"] = duration.group(1) + duration.group(2)
    if fields.get("amount_unit") in {"分钟", "小时", "秒", "min", "sec", "h"}:
        fields.pop("amount_value", None)
        fields.pop("amount_unit", None)

    # 试剂/仪器：只认方案里给出的术语，不自造词表
    for term in sorted(known_terms, key=len, reverse=True):
        if term and term in text:
            if "object" not in fields:
                fields["object"] = term
            elif "instrument" not in fields and term != fields.get("object"):
                fields["instrument"] = term
                break

    return ExperimentEntities(**fields)
