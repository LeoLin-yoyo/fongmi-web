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
    return {"code": 0, "data": {"has_cookie": bool(get_config_value("douyin_cookie"))}}


@router.post("/config")
async def set_config(req: ConfigRequest):
    set_config_value("douyin_cookie", (req.cookie or "").strip())
    return {"code": 0, "data": {"has_cookie": bool(req.cookie.strip())}}
