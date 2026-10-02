"""Image Proxy - bypass CORS for thumbnails

失败降级：返回带片名的占位海报 SVG（而非 1×1 透明像素，T5-1）。
成功结果进内存 LRU 缓存，减少重复外链请求。
"""
import html
import threading
from collections import OrderedDict

from fastapi import APIRouter, Query
from fastapi.responses import Response

from spider.proxy_config import get_proxy_with_detect

router = APIRouter(prefix="/img", tags=["img"])

_CACHE_MAX_ENTRIES = 500
_cache: "OrderedDict[str, tuple[bytes, str]]" = OrderedDict()
_cache_lock = threading.Lock()
_cache_hits = 0
_cache_misses = 0


def _cache_get(key: str):
    global _cache_hits
    with _cache_lock:
        item = _cache.get(key)
        if item is None:
            return None
        _cache.move_to_end(key)
        _cache_hits += 1
        return item


def _cache_put(key: str, content: bytes, media_type: str):
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
        _cache[key] = (content, media_type)
        while len(_cache) > _CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)


def cache_stats() -> dict:
    with _cache_lock:
        total = _cache_hits + _cache_misses
        return {"entries": len(_cache), "hits": _cache_hits, "misses": _cache_misses,
                "hit_rate": round(_cache_hits / total, 4) if total else 0.0}


def _placeholder_svg(name: str) -> bytes:
    """占位海报：深色底 + 胶片图标 + 可读片名"""
    display = (name or "").strip()
    # SVG 内手动换行：每行最多 10 个字符，最多 2 行
    lines = []
    if display:
        for i in range(0, min(len(display), 20), 10):
            lines.append(display[i:i + 10])
            if len(lines) >= 2:
                break
        if len(display) > 20:
            lines[-1] = lines[-1][:9] + "…"
    text_svg = ""
    for idx, line in enumerate(lines):
        y = 96 + idx * 22
        text_svg += (f'<text x="50" y="{y}" text-anchor="middle" fill="#9aa0a6" '
                     f'font-size="13" font-family="sans-serif">{html.escape(line)}</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 140">
<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#23233a"/><stop offset="1" stop-color="#14141f"/>
</linearGradient></defs>
<rect width="100" height="140" fill="url(#g)"/>
<g fill="none" stroke="#4a4a66" stroke-width="2">
<rect x="34" y="30" width="32" height="24" rx="3"/>
<circle cx="42" cy="42" r="3.5"/><circle cx="58" cy="42" r="3.5"/>
<circle cx="50" cy="36" r="3.5"/><circle cx="50" cy="48" r="3.5"/>
<path d="M44 30v24M56 30v24M34 42h32" stroke-width="1"/>
</g>
{text_svg}
</svg>'''
    return svg.encode("utf-8")


async def _fetch_image(url: str, headers: dict, proxy: str | None):
    """拉取图片；proxy 为 None 时直连"""
    import httpx
    async with httpx.AsyncClient(
        timeout=10.0, follow_redirects=True, headers=headers, proxy=proxy,
    ) as client:
        return await client.get(url)


@router.get("/proxy")
async def image_proxy(url: str = Query(...), name: str = Query(default="")):
    """Proxy image requests to bypass CORS; name 用于失败时的占位海报文案"""
    cached = _cache_get(url)
    if cached:
        content, media_type = cached
        return Response(content=content, media_type=media_type,
                        headers={"Cache-Control": "public, max-age=86400",
                                 "Access-Control-Allow-Origin": "*"})

    global _cache_misses
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.google.com/",
    }

    # 每次实时读配置：设置页改代理立即生效；未配置则依次回退系统代理、本机在跑的代理、直连
    proxy = get_proxy_with_detect() or None
    try:
        resp = await _fetch_image(url, headers, proxy)
    except Exception:
        if proxy:
            # 代理不可用时回退直连重试，代理异常不拖垮可达图床
            try:
                resp = await _fetch_image(url, headers, None)
            except Exception:
                resp = None
        else:
            resp = None

    if resp is None:
        return Response(content=_placeholder_svg(name), media_type="image/svg+xml",
                        headers={"Cache-Control": "no-store",
                                 "Access-Control-Allow-Origin": "*"})

    try:
        content_type = resp.headers.get("content-type", "image/jpeg")
        if not content_type.startswith("image/"):
            content_type = "image/jpeg"
        content = resp.content
        # 空/超小内容视为加载失败，同样降级占位
        if len(content) < 100:
            raise ValueError("image too small")
        with _cache_lock:
            _cache_misses += 1
        _cache_put(url, content, content_type)
        return Response(content=content, media_type=content_type,
                        headers={"Cache-Control": "public, max-age=86400",
                                 "Access-Control-Allow-Origin": "*"})
    except Exception:
        placeholder = _placeholder_svg(name)
        return Response(content=placeholder, media_type="image/svg+xml",
                        headers={"Cache-Control": "no-store",
                                 "Access-Control-Allow-Origin": "*"})
