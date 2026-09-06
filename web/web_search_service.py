# -*- coding: utf-8 -*-
"""联网检索服务：本地/社区找不到配方时，从公开网页检索并保存临时配方。

设计要点：
- 搜索走 DuckDuckGo HTML（无需 API key，部署环境可直连外网即可用）。
- 抓取网页正文后交给 LLM 结构化，落成本地试剂配置库的一条临时配方。
- 来源字段明确标记「网络检索（临时）」，并保留真实 source_url，
  前端试剂配置库会显示来源和链接，review_status=UNREVIEWED。
"""

from __future__ import annotations

import hashlib
import html as html_lib
import re
import uuid
from urllib.parse import parse_qs, unquote, urlparse

import httpx

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_DDG_HTML_URL = "https://html.duckduckgo.com/html/"
_BING_CN_URL = "https://cn.bing.com/search"
_TIMEOUT = httpx.Timeout(18.0, connect=8.0)


def _get(url: str, params: dict | None = None) -> httpx.Response:
    """统一网络请求：超时、跟随重定向、不读系统代理配置（避免和局域网冲突）。"""
    return httpx.get(
        url,
        params=params,
        headers={"User-Agent": _USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        timeout=_TIMEOUT,
        follow_redirects=True,
        trust_env=False,
    )


def _clean_text(text: str, max_chars: int = 0) -> str:
    """去掉 HTML 标签、脚本、多余空白。"""
    if not text:
        return ""
    # 去掉 script/style
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    # 去掉标签
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    # 压缩空白
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = text.strip()
    if max_chars and len(text) > max_chars:
        text = text[:max_chars]
    return text


def _ddg_real_url(href: str) -> str:
    """DuckDuckGo 结果链接可能是 /l/?uddg=... 跳转，解析出真实 URL。"""
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    try:
        parsed = urlparse(href)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            uddg = parse_qs(parsed.query).get("uddg", [None])[0]
            if uddg:
                return uddg
        if parsed.netloc in ("", "duckduckgo.com", "www.duckduckgo.com"):
            return ""
    except Exception:
        pass
    return href


def _bing_search_results(page: str, limit: int) -> list[dict]:
    """解析 Bing 搜索 HTML：<li class="b_algo"> 里的 h2/a/p。"""
    results: list[dict] = []
    blocks = re.split(r'class="b_algo"', page)
    for block in blocks[1:]:
        m = re.search(
            r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            block,
            flags=re.I | re.S,
        )
        if not m:
            continue
        url = html_lib.unescape(m.group(1)).strip()
        title = _clean_text(m.group(2))
        if not url.startswith("http") or not title:
            continue
        snip_m = re.search(r"<p[^>]*>(.*?)</p>", block, flags=re.I | re.S)
        snippet = _clean_text(snip_m.group(1), 300) if snip_m else ""
        results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= limit:
            break
    return results


# 无关域名：词典/百科/游戏/贴吧等，搜索科学配方时这些结果几乎都是噪音
_IRRELEVANT_DOMAINS = {
    "baike.baidu.com", "tieba.baidu.com", "iciba.com", "dictionary.cambridge.org",
    "zhidao.baidu.com", "wenku.baidu.com", "wikiwand.com",
    "translate.google.com", "fanyi.baidu.com", "dict.youdao.com",
    "bing.com", "google.com",
}
# 无关关键词出现在标题里 → 几乎可以判定为噪音
_IRRELEVANT_TITLE_HINTS = [
    "是什么意思", "翻译", "音标", "读音", "例句", "词典", "百科",
    "游戏", "推荐", "攻略", "对比", "排行",
]


def _domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def _is_relevant(result: dict, query: str) -> bool:
    """快速判断搜索结果是否可能是科学/实验相关内容，而非词典/游戏噪音。"""
    url = result.get("url", "")
    title = result.get("title", "")
    domain = _domain_of(url)
    if domain in _IRRELEVANT_DOMAINS:
        return False
    title_low = title.lower()
    for hint in _IRRELEVANT_TITLE_HINTS:
        if hint in title_low:
            return False
    return True


def _score_result(result: dict, query_terms: list[str]) -> int:
    """给搜索结果打相关性分数（越高越相关）。"""
    title = (result.get("title") or "").lower()
    snippet = (result.get("snippet") or "").lower()
    blob = title + " " + snippet
    score = 0
    for term in query_terms:
        t = term.lower().strip()
        if not t:
            continue
        if t in title:
            score += 3
        if t in snippet:
            score += 1
    return score


def web_search(query: str, limit: int = 5) -> list[dict]:
    """在公开网页搜索，返回 [{title, url, snippet}]。

    优先尝试 Bing CN（中国大陆可直连），失败/无结果再试 DuckDuckGo。
    所有引擎返回的结果都会经过域名过滤 + 相关性排序。
    若网络不通/搜索被限制，抛 RuntimeError 由上层转成友好提示。
    """
    errors: list[str] = []
    raw_results: list[dict] = []

    # 1. Bing CN
    try:
        resp = _get(_BING_CN_URL, params={"q": query, "setlang": "zh-hans", "ensearch": "0"})
        resp.raise_for_status()
        raw_results = _bing_search_results(resp.text, limit * 2)
    except Exception as error:
        errors.append(f"Bing 失败：{error}")

    # 2. Bing 没结果或太少 → 补 DuckDuckGo HTML
    if len(raw_results) < limit:
        try:
            resp = _get(_DDG_HTML_URL, params={"q": query, "kl": "cn-zh"})
            resp.raise_for_status()
            page = resp.text
            ddg = _parse_ddg_results(page, limit * 2)
            raw_results.extend(ddg)
        except Exception as error:
            if not raw_results:
                raise RuntimeError(
                    "联网搜索失败（Bing 和 DuckDuckGo 都不可用）："
                    + "；".join(errors + [f"DuckDuckGo 失败：{error}"])
                ) from error

    if not raw_results:
        raise RuntimeError("联网搜索没有返回任何结果。")

    # 统一去重
    seen = set()
    deduped = []
    for r in raw_results:
        key = r["url"]
        if key in seen or not r["url"].startswith(("http://", "https://")):
            continue
        seen.add(key)
        deduped.append(r)

    # 过滤噪音 + 相关性排序
    query_terms = [t.strip() for t in re.split(r"[\s,，、]+", query) if t.strip()]
    filtered = [r for r in deduped if _is_relevant(r, query)]
    if filtered:
        filtered.sort(key=lambda r: _score_result(r, query_terms), reverse=True)
        return filtered[:limit]
    if deduped:
        raise RuntimeError(
            f"搜索到了 {len(deduped)} 条结果但全部与科学配方无关"
            f"（被词典/百科/游戏类页面占据）。建议用更精确的英文学名或加引号，"
            f"例如 '\"SOB medium recipe tryptone\"' 或换用英文搜索。"
        )
    raise RuntimeError("联网搜索没有返回可用结果。")


def _parse_ddg_results(page: str, limit: int) -> list[dict]:
    """解析 DuckDuckGo HTML 结果页。"""
    results: list[dict] = []
    blocks = re.split(r'class="result[^"]*results_links[^"]*"', page)
    for block in blocks[1:]:
        m = re.search(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            block,
            flags=re.I | re.S,
        )
        if not m:
            continue
        url = _ddg_real_url(m.group(1))
        title = _clean_text(m.group(2))
        if not url or not title:
            continue
        snip_m = re.search(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            block,
            flags=re.I | re.S,
        )
        snippet = _clean_text(snip_m.group(1)) if snip_m else ""
        results.append({"title": title, "url": url, "snippet": snippet[:300]})
        if len(results) >= limit:
            break
    # 宽松兜底
    if not results:
        for m in re.finditer(
            r'<a[^>]*rel="nofollow"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            page,
            flags=re.I | re.S,
        ):
            url = _ddg_real_url(m.group(1))
            title = _clean_text(m.group(2))
            if url and title and not url.startswith("javascript:"):
                results.append({"title": title, "url": url, "snippet": ""})
                if len(results) >= limit:
                    break
    return results


def fetch_web_text(url: str, max_chars: int = 8000) -> dict:
    """抓取一个网页并提取纯文本，供 LLM 结构化配方。

    返回 {url, title, text}；网络/解析失败抛 RuntimeError。
    """
    if not url or not url.startswith(("http://", "https://")):
        raise RuntimeError("无效的网页地址。")
    try:
        resp = _get(url)
        resp.raise_for_status()
    except Exception as error:
        raise RuntimeError(f"抓取网页失败（{url}）：{error}") from error

    page = resp.text or ""
    title_m = re.search(r"<title[^>]*>(.*?)</title>", page, flags=re.I | re.S)
    title = _clean_text(title_m.group(1), 200) if title_m else url
    text = _clean_text(page, max_chars=max_chars)
    return {"url": url, "title": title, "text": text}


def _unique_web_id(name_zh: str, url: str) -> str:
    """生成一个不会和本地已有配方冲突的 web- 前缀 id。"""
    import domain

    slug = re.sub(r"[^A-Za-z0-9]+", "-", (name_zh or "web").strip().lower()).strip("-")
    if not slug:
        slug = "recipe"
    base = slug[:40]
    digest = hashlib.sha1((name_zh + "|" + url).encode("utf-8")).hexdigest()[:8]
    candidate = f"web-{base}-{digest}"
    # 若极端撞库，补随机后缀
    existing = {p.reagent_prep_id for p in domain.reagent_preps().list_all()}
    if candidate in existing:
        candidate = f"web-{base}-{uuid.uuid4().hex[:6]}"
    return candidate


def save_web_reagent_prep(
    query: str,
    url: str = "",
    description: str = "",
    max_results: int = 5,
) -> dict:
    """联网搜索→抓取网页→LLM 结构化→保存为临时网络配方。

    返回 domain.reagent_prep_view 同结构；任何一步失败抛 RuntimeError。
    """
    import domain
    import llm_bridge

    search_text = description or query
    chosen_url = (url or "").strip()

    # 1. 没有指定 URL → 先联网搜索
    if not chosen_url:
        results = web_search(search_text, limit=max(1, int(max_results)))
        if not results:
            raise RuntimeError(f"没有在公开网页找到「{search_text}」的相关结果。")
        # 按关键词相关性排序，选最匹配的网页（仍是网页真实来源）
        query_terms = [t.strip() for t in re.split(r"[\s,，、]+", search_text) if t.strip()]
        results.sort(key=lambda r: _score_result(r, query_terms), reverse=True)
        best = results[0]
        chosen_url = best["url"]
        candidates = results
    else:
        candidates = []

    # 2. 抓取网页正文
    page = fetch_web_text(chosen_url)

    # 3. LLM 从正文提取结构化配方
    draft = llm_bridge.generate_reagent_prep_from_web_text(
        page_title=page["title"],
        page_text=page["text"],
        source_url=chosen_url,
    )

    # 3b. 验证提取结果——如果网页内容和配方无关，LLM 可能返回空字段
    name = draft.get("name_zh") or ""
    steps = draft.get("steps") or []
    if not name.strip() or not steps:
        raise RuntimeError(
            f"已抓取网页「{page['title'][:60]}」但未能从中提取有效配方。"
            f"该页面可能不是配方/protocol 页面。"
            f"建议：(1) 直接告诉用户标准配方内容并手动创建；"
            f"(2) 或用户提供具体网址后再试。"
        )

    # 强制来源标记
    draft["source"] = "网络检索（临时）"
    draft["source_url"] = chosen_url
    draft["review_status"] = "UNREVIEWED"
    draft["reagent_prep_id"] = _unique_web_id(
        name, chosen_url
    )

    # 4. 落库
    saved = domain.add_reagent_prep(draft)
    saved["ui_action"] = {"type": "navigate", "view": "reagent_prep"}
    saved["web_search"] = {
        "query": search_text,
        "url": chosen_url,
        "is_network_source": True,
        "candidates": candidates[:max_results],
    }
    return saved
