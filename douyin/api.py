"""抖音 REST API（挂载于 /api/douyin）。

- POST /api/douyin/resolve        粘贴分享链接 → 作品信息（视频/图集/封面/音乐）
- GET  /api/douyin/stream/{token} 媒体代理（Range 透传，带 Referer/UA）
- POST /api/douyin/download       单个媒体加入统一下载引擎
- POST /api/douyin/download_all   整条作品（视频或全部图集）批量入队
- GET/POST /api/douyin/config     可选 Cookie（风控时提高成功率）
"""
import mimetypes
import os
import re

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from downloader import manager as dl_manager
from downloader.config import get_download_dir
from spider.proxy_config import get_config_value, get_proxy_with_detect, set_config_value

from .parser import REFERER, UA_MOBILE, DouyinError
from .resolver import resolve, take_link

router = APIRouter(prefix="/douyin", tags=["douyin"])

_MEDIA_MIME = {
    "video": "video/mp4", "image": "image/jpeg", "audio": "audio/mpeg",
}


class ResolveRequest(BaseModel):
    text: str


class DownloadRequest(BaseModel):
    token: str
    folder: str = ""


class DownloadAllRequest(BaseModel):
    tokens: list[str]
    folder: str = ""


class ConfigRequest(BaseModel):
    cookie: str = ""
    user_agent: str = ""


# Cookie 有效性判定所需的关键字段（抖音风控链）
_REQUIRED_COOKIE_KEYS = ("ttwid",)
_STRONG_COOKIE_KEYS = ("uifid", "UIFID", "msToken", "__ac_signature", "s_v_web_id")


def _media_headers() -> dict:
    h = {"User-Agent": UA_MOBILE, "Referer": REFERER, "Accept-Language": "zh-CN,zh;q=0.9"}
    cookie = (get_config_value("douyin_cookie") or "").strip()
    if cookie:
        h["Cookie"] = cookie
    return h


@router.post("/resolve")
async def resolve_endpoint(req: ResolveRequest):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(400, "请粘贴抖音分享链接或文案")
    try:
        data = await resolve(text)
    except DouyinError as e:
        raise HTTPException(422, f"解析失败：{e}")
    except Exception as e:
        raise HTTPException(422, f"解析失败：{str(e)[:160]}")
    return {"code": 0, "data": data}


@router.api_route("/stream/{token}", methods=["GET", "HEAD"])
async def stream(token: str, request: Request):
    """媒体代理：直链带 Referer/UA，Range 透传给播放器。"""
    link = take_link(token)
    if not link:
        raise HTTPException(410, "链接已过期，请重新解析")

    headers = _media_headers()
    rng = request.headers.get("range")
    if rng:
        headers["Range"] = rng

    ctype = _MEDIA_MIME.get(link["kind"]) or mimetypes.guess_type(link["filename"])[0] \
        or "application/octet-stream"

    if request.method == "HEAD":
        from fastapi.responses import Response
        return Response(status_code=200, media_type=ctype,
                        headers={"Accept-Ranges": "bytes"})

    kwargs = {}
    proxy = get_proxy_with_detect()
    if proxy:
        kwargs["proxy"] = proxy
    client = httpx.AsyncClient(follow_redirects=True, verify=False,
                               timeout=httpx.Timeout(20.0, read=120.0), **kwargs)
    req = client.build_request("GET", link["url"], headers=headers)
    try:
        upstream = await client.send(req, stream=True)
    except httpx.HTTPError as e:
        await client.aclose()
        raise HTTPException(502, f"上游连接失败: {str(e)[:100]}")

    if upstream.status_code not in (200, 206):
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(502, f"上游返回 HTTP {upstream.status_code}")

    resp_headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-store"}
    for h in ("content-range", "content-length"):
        if h in upstream.headers:
            resp_headers[h.title()] = upstream.headers[h]
    if "content-type" in upstream.headers:
        ctype = upstream.headers["content-type"]

    async def body():
        try:
            async for chunk in upstream.aiter_bytes(256 * 1024):
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(body(), media_type=ctype,
                             status_code=upstream.status_code, headers=resp_headers)


@router.post("/download")
async def download(req: DownloadRequest):
    link = take_link(req.token)
    if not link:
        raise HTTPException(410, "链接已过期，请重新解析")
    folder = (req.folder or get_download_dir()).strip()
    task_id = await dl_manager.add(
        source="douyin", name=link["filename"], url=link["url"], folder=folder,
        headers=_media_headers(), filename=link["filename"],
    )
    return {"code": 0, "id": task_id, "name": link["filename"]}


@router.post("/download_all")
async def download_all(req: DownloadAllRequest):
    if not req.tokens:
        raise HTTPException(400, "没有可下载的媒体")
    folder = (req.folder or get_download_dir()).strip()
    ids = []
    for token in req.tokens:
        link = take_link(token)
        if not link:
            continue
        task_id = await dl_manager.add(
            source="douyin", name=link["filename"], url=link["url"], folder=folder,
            headers=_media_headers(), filename=link["filename"],
        )
        ids.append(task_id)
    if not ids:
        raise HTTPException(410, "链接均已过期，请重新解析")
    return {"code": 0, "ids": ids, "count": len(ids)}


@router.get("/config")
async def get_config():
    cookie = (get_config_value("douyin_cookie") or "").strip()
    return {"code": 0, "data": {
        "has_cookie": bool(cookie),
        "has_uifid": _has_any(cookie, _STRONG_COOKIE_KEYS),
        "user_agent": get_config_value("douyin_ua") or "",
    }}


@router.post("/config")
async def set_config(req: ConfigRequest):
    cookie = (req.cookie or "").strip()
    set_config_value("douyin_cookie", cookie)
    set_config_value("douyin_ua", (req.user_agent or "").strip())
    return {"code": 0, "data": {
        "has_cookie": bool(cookie),
        "has_uifid": _has_any(cookie, _STRONG_COOKIE_KEYS),
    }}


@router.post("/verify")
async def verify_cookie():
    """用当前 Cookie 做一次真实探测，判断是否已越过 uifid 风控。

    探测方式：对 detail API 发一次带 a_bogus 签名的请求，看是否还返回 403。
    """
    from .parser import UA_DESKTOP
    from .resolver import _ensure_ttwid, _try_web_api

    cookie = (get_config_value("douyin_cookie") or "").strip()
    if not cookie:
        raise HTTPException(400, "尚未配置 Cookie")
    if not _has_any(cookie, _REQUIRED_COOKIE_KEYS):
        raise HTTPException(400, "Cookie 缺少 ttwid 字段，请复制完整 Cookie")

    import httpx as _httpx
    kwargs = {}
    proxy = get_proxy_with_detect()
    if proxy:
        kwargs["proxy"] = proxy
    async with _httpx.AsyncClient(follow_redirects=True, verify=False,
                                  timeout=25.0, **kwargs) as client:
        await _ensure_ttwid(client)
        # 用一个稳定存在的公开作品 ID 探测（不存在也无妨：能过风控就会返回业务错误而非 403）
        info = await _try_web_api("7531200000000000000", client)
    if info is not None:
        return {"code": 0, "data": {"ok": True, "detail": "Cookie 有效，已越过风控"}}
    return {"code": 1, "data": {
        "ok": False,
        "detail": "Cookie 未生效：仍被 uifid 风控拦截。请确认复制的是 www.douyin.com 的完整 Cookie"
                  "（含 uifid），并填写与该浏览器一致的 User-Agent",
    }}


def _has_any(cookie: str, keys) -> bool:
    low = (cookie or "").lower()
    return any(k.lower() in low for k in keys)
