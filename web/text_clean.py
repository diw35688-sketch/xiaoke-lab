# -*- coding: utf-8 -*-
"""清理 LLM 输出里混入的 Markdown 装饰符号。"""

from __future__ import annotations

import re
from typing import Any

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")


def clean_text(value: Any) -> Any:
    """递归去掉字符串里的 Markdown 星号、反引号和常见标题符号。"""

    if isinstance(value, str):
        text = _BOLD.sub(r"\1", value)
        text = _ITALIC.sub(r"\1", text)
        text = text.replace("`", "")
        text = text.replace("###", "").replace("##", "").replace("#", "")
        return text.strip()
    if isinstance(value, dict):
        return {key: clean_text(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_text(item) for item in value]
    if isinstance(value, tuple):
        return [clean_text(item) for item in value]
    return value
