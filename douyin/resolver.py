"""抖音解析编排：链接 → 作品信息 → 直链签发。

直链以 token 签发（与网盘模块同款），播放/下载字节流都经服务端代理，
外部无法借本模块请求任意 URL（SSRF 防线）。
"""
import asyncio
import secrets
import time
from collections import OrderedDict

import httpx
from loguru import logger

from spider.proxy_config import get_config_value, get_proxy_with_detect

from .link import extract_url, parse_aweme_id
from .parser import (
    REFERER,
    UA_DESKTOP,
    UA_MOBILE,
    DouyinError,
    no_watermark,
    parse_page,
    share_page_candidates,
)

# token → (url, kind, filename, 过期时间)
_LINKS: OrderedDict[str, tuple] = OrderedDict()
_LINK_TTL = 3 * 3600
_LINK_MAX = 300

_VIDEO_EXT = {"mp4", "m4v", "webm", "mov"}


def _put(key: str, value) -> str:
    _LINKS[key] = value
    while len(_LINKS) > _LINK_MAX:
        _LINKS.popitem(last=False)
    return key


def take_link(token: str):
    entry = _LINKS.get(token)
    if not entry:
        return None
    url, kind, filename, exp = entry
    if exp < time.monotonic():
        _LINKS.pop(token, None)
        return None
    return {"url": url, "kind": kind, "filename": filename}


def _issue(url: str, kind: str, filename: str) -> str:
    token = secrets.token_urlsafe(9)
    return _put(token, (url, kind, filename, time.monotonic() + _LINK_TTL))


def _cfg_cookie() -> str:
    return (get_config_value("douyin_cookie") or "").strip()


def _cfg_ua(default: str) -> str:
    """UA 配置：a_bogus 签名与 Cookie 都绑定 UA，二者必须来自同一浏览器。

    用户在「风控 Cookie」里粘贴浏览器 Cookie 时，若同时填了 UA，则全链路统一使用。
    """
    return (get_config_value("douyin_ua") or "").strip() or default


def _headers(extra: dict | None = None, ua: str | None = None) -> dict:
    h = {"User-Agent": ua or _cfg_ua(UA_MOBILE), "Referer": REFERER,
         "Accept-Language": "zh-CN,zh;q=0.9"}
    cookie = _cfg_cookie()
    if cookie:
        h["Cookie"] = cookie
    h.update(extra or {})
    return h


def _client() -> httpx.AsyncClient:
    kwargs = dict(follow_redirects=True, verify=False, timeout=httpx.Timeout(20.0, read=40.0))
    proxy = get_proxy_with_detect()
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.AsyncClient(**kwargs)


async def _ensure_ttwid(client: httpx.AsyncClient) -> str:
    """获取 ttwid（抖音风控基础 cookie）。返回当前 cookie 串。"""
    try:
        await client.post(
            "https://ttwid.bytedance.com/ttwid/union/register/",
            json={"region": "cn", "aid": 1768, "needFid": False,
                  "service": "www.ixigua.com",
                  "migrate_info": {"ticket": "", "source": "node"},
                  "cbUrlProtocol": "https", "union": True},
            headers={"User-Agent": UA_MOBILE, "Content-Type": "application/json"},
        )
    except httpx.HTTPError as e:
        logger.debug(f"ttwid 获取失败: {e}")
    cookie = (get_config_value("douyin_cookie") or "").strip()
    jar = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
    if cookie and jar:
        return f"{cookie}; {jar}"
    return cookie or jar


async def resolve_aweme_id(url: str, client: httpx.AsyncClient) -> str:
    """从链接解析 aweme_id（短链跟随重定向）。"""
    direct = parse_aweme_id(url)
    if direct:
        return direct
    try:
        resp = await client.get(url, headers=_headers())
    except httpx.HTTPError as e:
        raise DouyinError(f"短链解析失败：{str(e)[:100]}") from e
    got = parse_aweme_id(str(resp.url))
    if not got:
        raise DouyinError("无法解析作品 ID（链接可能已失效）")
    return got


async def fetch_share_page(aweme_id: str, client: httpx.AsyncClient) -> str:
    """抓分享页 HTML（视频/图集/笔记三种形态逐个尝试）。

    抖音对匿名请求会返回「空壳页」（HTTP 200 但无 videoInfoRes），
    因此以「页面是否真的带回作品数据」作为成功判据。
    """
    from .parser import has_aweme_data

    last = ""
    for page in share_page_candidates(aweme_id):
        for attempt in range(3):
            try:
                resp = await client.get(page, headers=_headers())
                if resp.status_code == 200 and resp.text:
                    last = resp.text
                    if has_aweme_data(last):
                        return last
                    break  # 空壳页：换下一种形态，不必重试同一地址
            except httpx.HTTPError as e:
                last = ""
                logger.debug(f"抖音分享页请求失败 {page}: {e}")
            await asyncio.sleep(1.0 * (attempt + 1))
    if last:
        return last  # 交给 parse_page 区分「风控空壳」与「作品不存在」
    raise DouyinError("抓取分享页失败（请检查网络或代理）")


async def resolve(text: str) -> dict:
    """粘贴文本 → 作品信息 + 已签发的播放/下载地址。"""
    url = extract_url(text or "")
    if not url:
        raise DouyinError("未找到抖音链接")
    async with _client() as client:
        aweme_id = await resolve_aweme_id(url, client)
        await _ensure_ttwid(client)
        # 路径 1：Web detail API（a_bogus 签名）
        info = await _try_web_api(aweme_id, client)
        # 路径 2：分享页 SSR 数据
        if info is None:
            html = await fetch_share_page(aweme_id, client)
            info = parse_page(html)
    info["aweme_id"] = info.get("aweme_id") or aweme_id

    out = {
        "aweme_id": info["aweme_id"],
        "type": info["type"],
        "title": info["title"],
        "author": info["author"],
        "video": None, "cover": None, "music": None, "images": [],
    }
    if info["type"] == "video" and info["video_url"]:
        clean = no_watermark(info["video_url"])
        name = f"{info['author']}_{info['title']}".strip("_") or f"douyin_{info['aweme_id']}"
        token = _issue(clean, "video", f"{name}.mp4")
        out["video"] = {"token": token, "stream_path": f"/api/douyin/stream/{token}",
                        "playable": True, "filename": f"{name}.mp4"}
    for i, img in enumerate(info["images"], 1):
        token = _issue(img, "image", f"{info['aweme_id']}_{i:02d}.jpg")
        out["images"].append({"token": token, "path": f"/api/douyin/stream/{token}",
                              "index": i})
    if info["cover_url"]:
        token = _issue(info["cover_url"], "image", f"{info['aweme_id']}_cover.jpg")
        out["cover"] = {"token": token, "path": f"/api/douyin/stream/{token}"}
    if info["music_url"]:
        token = _issue(info["music_url"], "audio", f"{info['aweme_id']}.mp3")
        out["music"] = {"token": token, "path": f"/api/douyin/stream/{token}"}
    return out


async def _try_web_api(aweme_id: str, client: httpx.AsyncClient) -> dict | None:
    """尝试 Web detail API（带 a_bogus 签名）。失败返回 None 交给 SSR 路径。"""
    from .parser import UA_DESKTOP, parse_aweme

    try:
        from .abogus import ABogus
    except Exception:
        return None

    from urllib.parse import urlencode
    params = {
        "device_platform": "webapp", "aid": "6383", "channel": "channel_pc_web",
        "aweme_id": aweme_id, "pc_client_type": "1", "version_code": "190500",
        "version_name": "19.5.0", "cookie_enabled": "true", "platform": "PC",
        "browser_name": "Chrome", "browser_version": "131.0.0.0",
        "browser_language": "zh-CN", "browser_platform": "Win32",
        "browser_online": "true", "engine_name": "Blink", "engine_version": "131.0.0.0",
        "os_name": "Windows", "os_version": "10", "cpu_core_num": "12",
        "device_memory": "8", "screen_width": "1920", "screen_height": "1080",
    }
    query = urlencode(params)
    try:
        sig = ABogus(UA_DESKTOP).get_value(query, "GET")
    except Exception as e:
        logger.debug(f"a_bogus 生成失败: {e}")
        return None

    url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/?{query}&a_bogus={sig}"
    headers = {
        "User-Agent": UA_DESKTOP,
        "Referer": f"https://www.douyin.com/video/{aweme_id}",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    cookie = (get_config_value("douyin_cookie") or "").strip()
    jar = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
    if cookie and jar:
        headers["Cookie"] = f"{cookie}; {jar}"
    elif cookie or jar:
        headers["Cookie"] = cookie or jar
    try:
        resp = await client.get(url, headers=headers)
    except httpx.HTTPError as e:
        logger.debug(f"抖音 detail API 请求失败: {e}")
        return None
    if resp.status_code != 200:
        logger.debug(f"抖音 detail API HTTP {resp.status_code}: {resp.text[:120]}")
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    detail = data.get("aweme_detail")
    if not isinstance(detail, dict):
        logger.debug(f"抖音 detail API 无 aweme_detail: {resp.text[:120]}")
        return None
    info = parse_aweme({"aweme": detail})
    # API 返回了 aweme_detail 但取不到视频/图集地址（可能是审核/地区限制）
    return info if info.get("type") != "unknown" else None
