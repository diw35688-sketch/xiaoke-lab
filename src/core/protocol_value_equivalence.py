"""Deterministic equivalence rules for protocol values and observed entities."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Iterable


_ACTION_EQUIVALENTS = {
    "称取": "称量",
    "称重": "称量",
}

_UNIT_EQUIVALENTS = {
    "克": "g",
    "公克": "g",
    "毫克": "mg",
    "微克": "μg",
    "毫升": "ml",
    "微升": "μl",
    "升": "l",
}


def normalize_protocol_value(field_name: str, value: str) -> str:
    """Return a conservative canonical form; never infer domain-specific aliases."""

    normalized = re.sub(r"\s+", "", value.strip()).casefold()
    if field_name == "action":
        return _ACTION_EQUIVALENTS.get(normalized, normalized)
    if field_name == "amount_unit":
        return _UNIT_EQUIVALENTS.get(normalized, normalized)
    if field_name == "amount_value":
        try:
            return str(Decimal(normalized).normalize())
        except InvalidOperation:
            return normalized
    if field_name == "temperature":
        return normalized.replace("摄氏度", "℃")
    return normalized


def protocol_values_equivalent(
    field_name: str,
    protocol_value: str,
    actual_value: str,
    *,
    aliases: Iterable[str] = (),
) -> bool:
    """Compare against the protocol value and aliases after common normalization."""

    actual = normalize_protocol_value(field_name, actual_value)
    candidates = (protocol_value, *tuple(aliases))
    return any(
        actual == normalize_protocol_value(field_name, candidate)
        for candidate in candidates
    )
