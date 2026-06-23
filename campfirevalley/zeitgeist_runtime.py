import asyncio
import html
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse
import base64

import aiohttp

from .zeitgeist_plugins import build_plugin_context


def _strip_html(text: str) -> str:
    if not text:
        return ""
    t = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    t = re.sub(r"(?is)<style.*?>.*?</style>", " ", t)
    t = re.sub(r"(?is)<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _extract_urls(text: str) -> List[str]:
    if not text:
        return []
    urls = re.findall(r"(https?://[^\s<>()]+)", text)
    clean = []
    for u in urls:
        u = u.strip().rstrip(").,;]")
        if u.startswith("http://") or u.startswith("https://"):
            clean.append(u)
    return clean[:3]

def _extract_image_urls(text: str) -> List[str]:
    urls = _extract_urls(text)
    out: List[str] = []
    for u in urls:
        low = u.lower()
        if any(low.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]):
            out.append(u)
    return out[:2]


def _should_web_search(user_text: str) -> bool:
    t = (user_text or "").lower()
    if "http://" in t or "https://" in t:
        return True
    triggers = [
        "search", "look up", "find", "latest", "today", "current", "news",
        "release", "version", "docs", "documentation", "spec", "price",
        "who is", "what is", "when did", "where is", "how many",
    ]
    return any(k in t for k in triggers)


async def web_search(query: str, max_results: int = 5, timeout_s: float = 8.0) -> List[Dict[str, str]]:
    q = (query or "").strip()
    if not q:
        return []
    url = "https://lite.duckduckgo.com/lite/"
    params = {"q": q}
    headers = {"User-Agent": "CampfireValley/1.0 (+https://localhost)"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=timeout_s)) as resp:
            if resp.status != 200:
                return []
            body = await resp.text()
    items: List[Dict[str, str]] = []
    for m in re.finditer(r"(?is)<a[^>]*\bresult-link\b[^>]*>.*?</a>", body):
        anchor = m.group(0) or ""
        hm = re.search(r"(?is)href=['\"]([^'\"]+)['\"]", anchor)
        tm = re.search(r"(?is)>(.*?)</a>", anchor)
        raw_link = html.unescape((hm.group(1) if hm else "") or "").strip()
        if raw_link.startswith("//"):
            raw_link = "https:" + raw_link
        link = raw_link
        try:
            pu = urlparse(raw_link)
            if "duckduckgo.com" in (pu.netloc or "") and pu.path.startswith("/l/"):
                q = parse_qs(pu.query or "")
                uddg = q.get("uddg", [None])[0]
                if uddg:
                    link = unquote(uddg)
        except Exception:
            link = raw_link
        title = _strip_html((tm.group(1) if tm else "") or "")
        snippet = ""
        try:
            tail = body[m.end() : m.end() + 1200]
            sm = re.search(r"(?is)class=['\"]result-snippet['\"][^>]*>(.*?)</td>", tail)
            if sm:
                snippet = _strip_html(sm.group(1) or "")[:300]
        except Exception:
            snippet = ""
        if not link or not title:
            continue
        items.append({"title": title, "url": link, "snippet": snippet})
        if len(items) >= max_results:
            break
    if not items:
        for m in re.finditer(r'(?is)<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', body):
            link = html.unescape(m.group(1) or "").strip()
            title = _strip_html(m.group(2) or "")
            if not link or not title:
                continue
            if "duckduckgo.com" in link:
                continue
            items.append({"title": title, "url": link, "snippet": ""})
            if len(items) >= max_results:
                break
    return items[:max_results]


async def fetch_url_text(url: str, timeout_s: float = 8.0, max_chars: int = 8000) -> str:
    u = (url or "").strip()
    if not u.startswith("http://") and not u.startswith("https://"):
        return ""
    headers = {"User-Agent": "CampfireValley/1.0 (+https://localhost)"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(u, timeout=aiohttp.ClientTimeout(total=timeout_s)) as resp:
            if resp.status != 200:
                return ""
            body = await resp.text(errors="ignore")
    text = _strip_html(body)
    return text[:max_chars]

async def _fetch_bytes(url: str, timeout_s: float = 10.0, max_bytes: int = 10_000_000) -> bytes:
    u = (url or "").strip()
    if not u.startswith("http://") and not u.startswith("https://"):
        return b""
    headers = {"User-Agent": "CampfireValley/1.0 (+https://localhost)"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(u, timeout=aiohttp.ClientTimeout(total=timeout_s)) as resp:
            if resp.status != 200:
                return b""
            data = await resp.read()
    if len(data) > max_bytes:
        return b""
    return data


async def ollama_image_ocr(ollama_host: str, model: str, image_bytes: bytes, timeout_s: float = 30.0) -> str:
    if not ollama_host or not model or not image_bytes:
        return ""
    host = ollama_host.rstrip("/")
    b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": model,
        "prompt": "Extract all readable text from this image. Return only the extracted text.",
        "images": [b64],
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(f"{host}/api/generate", json=payload, timeout=aiohttp.ClientTimeout(total=timeout_s)) as resp:
            if resp.status != 200:
                return ""
            data = await resp.json()
    text = (data or {}).get("response") or ""
    return str(text).strip()


async def build_zeitgeist_context(user_text: str, zeitgeist_cfg: Dict[str, Any]) -> str:
    if not (zeitgeist_cfg or {}).get("enabled"):
        return ""
    blocks: List[str] = []
    if zeitgeist_cfg.get("web_search") and _should_web_search(user_text):
        results = await web_search(user_text, max_results=5)
        if results:
            lines = []
            for i, r in enumerate(results, start=1):
                snip = (r.get("snippet") or "").strip()
                if snip:
                    lines.append(f"{i}. {r.get('title','')} — {r.get('url','')}\n   {snip}".strip())
                else:
                    lines.append(f"{i}. {r.get('title','')} — {r.get('url','')}".strip())
            blocks.append("Web search results:\n" + "\n".join(lines))
            top_urls = [r.get("url") for r in results if r.get("url")]
            excerpt_texts: List[str] = []
            for u in top_urls[:2]:
                try:
                    t = await fetch_url_text(u, max_chars=6000)
                except Exception:
                    t = ""
                if t:
                    excerpt_texts.append(f"Source: {u}\n{t[:1200]}")
                await asyncio.sleep(0)
            if excerpt_texts:
                blocks.append("Top source excerpts:\n" + "\n\n".join(excerpt_texts))
    urls = _extract_urls(user_text)
    if zeitgeist_cfg.get("web_search") and urls:
        url_texts: List[str] = []
        for u in urls[:2]:
            try:
                t = await fetch_url_text(u)
            except Exception:
                t = ""
            if t:
                url_texts.append(f"Source: {u}\n{t[:1500]}")
            await asyncio.sleep(0)
        if url_texts:
            blocks.append("Web page excerpts:\n" + "\n\n".join(url_texts))
    plugin_block = await build_plugin_context(user_text, zeitgeist_cfg)
    if plugin_block:
        blocks.append(plugin_block)
    if not blocks:
        return ""
    if zeitgeist_cfg.get("image_ocr"):
        model = (zeitgeist_cfg.get("ollama_model") or "").strip()
        host = (zeitgeist_cfg.get("ollama_host") or "").strip()
        img_urls = _extract_image_urls(user_text)
        ocr_parts: List[str] = []
        for u in img_urls:
            try:
                b = await _fetch_bytes(u)
                txt = await ollama_image_ocr(host, model, b) if b else ""
            except Exception:
                txt = ""
            if txt:
                ocr_parts.append(f"Image OCR ({u}):\n{txt[:3000]}")
            await asyncio.sleep(0)
        if ocr_parts:
            blocks.append("\n\n".join(ocr_parts))
    return "\n\n".join(blocks).strip() + "\n\n"
