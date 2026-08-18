# -*- coding: utf-8 -*-
"""文档识别桥：调用科大统一 API 的 OCR 模型，把 PDF/图片转成文字，
再让文字模型把文字拆成多份结构化实验方案草稿。
"""

from __future__ import annotations

import base64
import io
import json

import httpx

# 科大统一 API 上经过实测可用的 OCR 模型。
OCR_MODEL = "unlimited-ocr"


def _auth_headers(settings) -> dict:
    return {
        "Authorization": "Bearer " + settings.api_key,
        "Content-Type": "application/json",
    }


def _mineru_key(settings) -> str:
    return settings.mineru_api_key or settings.key_for("ustc") or settings.api_key


def _ocr_key(settings) -> str:
    return settings.ocr_api_key or settings.key_for("ustc") or settings.api_key


def pdf_to_images(pdf_bytes: bytes) -> list[bytes]:
    """把 PDF 每页渲染成 PNG 字节。"""

    import fitz

    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    images: list[bytes] = []
    try:
        for page in document:
            pix = page.get_pixmap(dpi=144)
            images.append(pix.tobytes("png"))
    finally:
        document.close()
    if not images:
        raise ValueError("PDF 没有可识别页面。")
    return images


def ocr_image(settings, image_bytes: bytes, mime: str = "image/png") -> str:
    """调用 OCR 模型识别一张图片。"""

    url = settings.ocr_base_url.rstrip("/") + "/chat/completions"
    data_url = f"data:{mime};base64," + base64.b64encode(image_bytes).decode()
    payload = {
        "model": settings.ocr_model or OCR_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Parse this image to Markdown"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "max_tokens": 4000,
    }
    response = httpx.post(
        url,
        headers={
            "Authorization": "Bearer " + _ocr_key(settings),
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=httpx.Timeout(120, connect=10),
        trust_env=False,
    )
    response.raise_for_status()
    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise RuntimeError("OCR 返回格式异常：" + str(data)[:200])
    return content or ""


def _mineru_file_parse_url(settings) -> str:
    """从 OpenAI 兼容 base_url 推导科大 MinerU 服务地址。"""

    origin = settings.base_url.rstrip("/")
    if origin.endswith("/v1"):
        origin = origin[:-3]
    return origin + "/mineru/file_parse"


def parse_pdf_with_mineru(settings, pdf_bytes: bytes) -> str:
    """调用科大 MinerU 文件解析服务，返回 Markdown。"""

    url = settings.mineru_file_parse_url or _mineru_file_parse_url(settings)
    response = httpx.post(
        url,
        headers={"Authorization": "Bearer " + _mineru_key(settings)},
        data={"return_md": "true", "response_format_zip": "false"},
        files={"files": ("protocol.pdf", pdf_bytes, "application/pdf")},
        timeout=httpx.Timeout(180, connect=10),
        trust_env=False,
    )
    response.raise_for_status()
    data = response.json()
    results = data.get("results", {})
    parts: list[str] = []
    for item in results.values():
        if isinstance(item, dict) and item.get("md_content"):
            parts.append(item["md_content"])
    if not parts:
        raise ValueError("MinerU 没有返回解析内容：" + str(data)[:300])
    return "\n\n".join(parts)


def ocr_pdf(settings, pdf_bytes: bytes) -> str:
    """PDF → 优先 MinerU 文件解析；失败时回退逐页 OCR。"""

    try:
        return parse_pdf_with_mineru(settings, pdf_bytes)
    except Exception:
        pages = pdf_to_images(pdf_bytes)
        parts = [ocr_image(settings, page) for page in pages]
        return "\n\n".join(parts)


def extract_protocol_drafts(settings, ocr_text: str) -> list[dict]:
    """从 OCR 文本中识别出所有实验，生成多份 Protocol JSON 草稿。"""

    if not ocr_text.strip():
        raise ValueError("没有识别到文字。")

    url = settings.base_url.rstrip("/") + "/chat/completions"
    system_prompt = (
        "你是实验方案结构化助手。请从下面 OCR 识别出的实验讲义中找出所有独立实验，"
        "为每个实验生成一份完整实验方案 JSON。只输出 JSON，不要 Markdown，不要解释。"
        "格式为："
        '{"protocols":[{"protocol_id":"英文短横线id","title":"方案标题","source":"OCR识别草稿",'
        '"version":"1.0","schema_version":1,'
        '"steps":[{"step_number":1,"title":"步骤标题","instruction":"步骤说明",'
        '"protocol_values":{"字段名":"值"},"must_record":["字段名"],"terms":["术语"],'
        '"hazard_note":"安全提示或null","field_prompts":{"字段名":"追问话术"}}]}]}'
        "如果原文只有一个实验，就只返回一个。步骤至少 1 步。"
        "字段名只能使用：action, object, amount_value, amount_unit, concentration, "
        "temperature, duration, condition, observation, instrument。"
    )
    payload = {
        "model": settings.model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": ocr_text[:12000]},
        ],
        "max_tokens": 6000,
    }
    response = httpx.post(
        url,
        headers=_auth_headers(settings),
        json=payload,
        timeout=httpx.Timeout(180, connect=10),
        trust_env=False,
    )
    response.raise_for_status()
    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise RuntimeError("LLM 返回格式异常：" + str(data)[:200])
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:]
    try:
        parsed = json.loads(content)
        protocols = parsed.get("protocols", [parsed])
    except json.JSONDecodeError as error:
        raise RuntimeError("LLM 没有返回合法 JSON：" + str(error))
    if not isinstance(protocols, list) or not protocols:
        raise RuntimeError("没有识别到实验方案。")
    return protocols
