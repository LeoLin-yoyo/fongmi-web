"""抖音分享页数据提取与解析（移植社区公开的 `_ROUTER_DATA` 思路）。

页面内嵌两种形态：
- ``window._ROUTER_DATA = {...}``（脚本内联 JSON）
- ``<script id="RENDER_DATA" type="application/json">``（URL 编码的 JSON）

从中定位 aweme 对象，取出无水印播放地址、封面、图集、背景音乐。
无水印原理：地址中的 ``playwm`` 换成 ``play``。
"""
import json
import re
from urllib.parse import unquote

UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
REFERER = "https://www.douyin.com/"


class DouyinError(Exception):
    """抖音解析错误。"""


# 统一的风控提示：抖音 2026 起对匿名请求要求浏览器 JS 生成的 uifid
_BLOCKED_HINT = (
    "抖音风控拦截：需要浏览器环境生成的 uifid，当前纯 HTTP 签名不足。"
    "请在「风控 Cookie」中粘贴完整浏览器 Cookie（含 uifid）后重试")


# ---------- 页面 JSON 提取 ----------

_ROUTER_MARK = "window._ROUTER_DATA"
_RENDER_RE = re.compile(
    r'<script\s+id="RENDER_DATA"\s+type="application/json"[^>]*>(.*?)</script>', re.S)


def _balanced_json(text: str, start: int) -> str | None:
    """从 text[start]（应为 '{'）起，按花括号配对截取完整 JSON 串。"""
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def extract_page_json(html: str) -> dict | None:
    """从分享页 HTML 提取内嵌 JSON（_ROUTER_DATA 优先，RENDER_DATA 兜底）。"""
    if not html:
        return None
    idx = html.find(_ROUTER_MARK)
    while idx >= 0:
        brace = html.find("{", idx)
        if brace >= 0:
            chunk = _balanced_json(html, brace)
            if chunk:
                try:
                    return json.loads(chunk)
                except json.JSONDecodeError:
                    pass
        idx = html.find(_ROUTER_MARK, idx + 1)

    m = _RENDER_RE.search(html)
    if m:
        try:
            return json.loads(unquote(m.group(1)))
        except json.JSONDecodeError:
            pass
    return None


# ---------- aweme 定位 ----------

def _walk(obj, key: str):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _walk(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _walk(v, key)
            if r is not None:
                return r
    return None


def _looks_like_aweme(o) -> bool:
    return isinstance(o, dict) and any(k in o for k in ("desc", "video", "images", "aweme_id"))


def find_aweme(data) -> dict | None:
    """在嵌套 JSON 中定位真正的作品对象。"""
    if not isinstance(data, dict):
        return None
    r = _walk(data, "aweme")
    if isinstance(r, dict):
        return r
    r = _walk(data, "item_list")
    if isinstance(r, list) and r and isinstance(r[0], dict):
        return r[0]
    if _looks_like_aweme(data):
        return data

    def rec(o):
        if _looks_like_aweme(o):
            return o
        if isinstance(o, dict):
            for v in o.values():
                got = rec(v)
                if got is not None:
                    return got
        elif isinstance(o, list):
            for v in o:
                got = rec(v)
                if got is not None:
                    return got
        return None
    return rec(data)


def _first_url(node, *keys) -> str | None:
    """从 url_list / urlList / url 等形态取第一个 http 地址。"""
    if not isinstance(node, dict):
        return None
    for k in keys:
        v = node.get(k)
        if isinstance(v, list) and v:
            return v[0]
        if isinstance(v, str) and v.startswith("http"):
            return v
    for k in ("url_list", "urlList"):
        v = node.get(k)
        if isinstance(v, list) and v:
            return v[0]
    return None


def no_watermark(url: str) -> str:
    """playwm → play，得到无水印地址。"""
    if not url:
        return url
    return url.replace("/playwm/", "/play/").replace("playwm", "play")


# ---------- 作品解析 ----------

def parse_aweme(data: dict) -> dict:
    """从页面数据提取作品信息。"""
    info = {"type": "unknown", "title": "", "author": "", "aweme_id": "",
            "video_url": None, "cover_url": None, "images": [], "music_url": None}
    detail = find_aweme(data)
    if not isinstance(detail, dict):
        return info

    info["aweme_id"] = str(detail.get("aweme_id") or "")
    info["title"] = (detail.get("desc")
                     or (detail.get("share_info") or {}).get("share_title") or "").strip()
    author = detail.get("author") or {}
    if isinstance(author, dict):
        info["author"] = (author.get("nickname") or author.get("unique_id") or "").strip()

    video = detail.get("video") or {}
    if isinstance(video, dict):
        play = video.get("play_addr") or video.get("playAddr") or {}
        url = _first_url(play, "url_list", "urlList")
        if url:
            info["video_url"] = url
            info["type"] = "video"
        cover = video.get("cover") or video.get("origin_cover") or {}
        if isinstance(cover, dict):
            info["cover_url"] = _first_url(cover, "url_list", "urlList")
        elif isinstance(cover, str) and cover.startswith("http"):
            info["cover_url"] = cover

    images = detail.get("images")
    if isinstance(images, list) and images:
        urls = []
        for im in images:
            if not isinstance(im, dict):
                continue
            u = _first_url(im, "url_list", "urlList")
            if u:
                urls.append(u)
        if urls:
            info["images"] = urls
            info["type"] = "images"

    music = detail.get("music") or {}
    if isinstance(music, dict):
        info["music_url"] = _first_url(music.get("play_url") or {}, "url_list", "urlList")
    return info


def looks_dead(data) -> bool:
    """判断是否为「作品不存在 / 已删除 / 私密」的数据形态。"""
    if not isinstance(data, dict):
        return False
    loader = data.get("loaderData")
    if isinstance(loader, dict):
        for key, val in loader.items():
            if "video" not in key:
                continue
            if val is None:
                return True
            if isinstance(val, dict) and val.get("videoInfoRes") is None:
                return True
    return False


def has_aweme_data(html: str) -> bool:
    """分享页是否真的带回了作品数据。

    注意：抖音空壳页里也会出现 `videoInfoRes` 字样（键名存在但值为 null，
    或出现在其他 layout 分支），所以必须检查是否存在非空的 item_list。
    """
    if not html or "videoInfoRes" not in html:
        return False
    data = extract_page_json(html)
    if not data:
        return False
    loader = data.get("loaderData")
    if not isinstance(loader, dict):
        return False
    for key, val in loader.items():
        if not isinstance(val, dict):
            continue
        res = val.get("videoInfoRes")
        if isinstance(res, dict) and res.get("item_list"):
            return True
    return False



def parse_page(html: str) -> dict:
    """完整流程：HTML → 作品信息。失败抛 DouyinError。"""
    data = extract_page_json(html)
    if not data:
        raise DouyinError(_BLOCKED_HINT)
    info = parse_aweme(data)
    if info["type"] == "unknown":
        # 关键区分：页面根本没有作品数据（平台收紧/风控） vs 作品确实不存在
        if not has_aweme_data(html):
            raise DouyinError(_BLOCKED_HINT)
        if looks_dead(data):
            raise DouyinError("该作品不存在、已删除，或为私密/地区限制内容")
        raise DouyinError("未能识别作品类型（视频或图集）")
    return info


def share_page_candidates(aweme_id: str) -> list[str]:
    """分享页候选地址（视频 / 图集 / 笔记三种形态，逐个尝试）。"""
    return [
        f"https://www.iesdouyin.com/share/video/{aweme_id}/",
        f"https://www.iesdouyin.com/share/slides/{aweme_id}/",
        f"https://www.iesdouyin.com/share/note/{aweme_id}/",
    ]
