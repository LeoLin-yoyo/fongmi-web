"""网盘 REST API（挂载于 /api/pan）。

安全口径（继承两个参考项目的教训）：
- 字节流只认服务端签发的 token，token 换回「直链 + 绑定请求头」，
  外部无法借本接口请求任意 URL（SSRF 防线，对齐 tdl-web「请求目标由硬编码主机构造」）
- 解析输入只提取分享短码/提取码，拼平台固定端点，不直接 fetch 用户给的任意文本
"""
import re
import mimetypes
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from downloader.config import get_download_dir
from downloader import manager
from spider.proxy_config import get_proxy_with_detect

from . import accounts, resolver
from .link import SUPPORTED_PLATFORMS, parse_share_link, platform_label
from .models import PanError, ShareFile

router = APIRouter(prefix="/pan", tags=["pan"])


class ResolveRequest(BaseModel):
    text: str                 # 粘贴的分享链接（可带提取码文案）
    passcode: str = ""        # 手动补充的提取码（优先于文案识别）


class BrowseRequest(BaseModel):
    platform: str
    share_id: str
    passcode: str = ""
    pdir_fid: str = "0"       # 目录 fid；根目录为 0
    path: str = ""            # 前端面包屑路径，仅回填展示


class LinkRequest(BaseModel):
    platform: str
    share_id: str
    passcode: str = ""
    fid: str
    pdir_fid: str = "0"       # 文件所在目录（来自当前列表页），避免全树搜索


class DownloadRequest(BaseModel):
    token: str                # /link 签发的令牌
    folder: str = ""          # 空 = 设置中的全局下载目录


class AccountRequest(BaseModel):
    platform: str
    cookie: str


def _unsupported(platform: str):
    raise HTTPException(400, f"暂不支持的平台: {platform}")


def _file_dict(f: ShareFile, path: str = "") -> dict:
    d = f.to_dict()
    d["path"] = (path.rstrip("/") + "/" + d["fname"]) if path else d["fname"]
    return d


# ---------- 平台与解析 ----------

@router.get("/platforms")
async def list_platforms():
    """已支持解析的平台（前端据此渲染登录入口）。"""
    return {"code": 0, "data": [
        {"key": k, "label": platform_label(k)} for k in SUPPORTED_PLATFORMS
    ]}


@router.post("/resolve")
async def resolve(req: ResolveRequest):
    """粘贴文本 → 识别平台 + 短码 + 提取码 → 解析分享会话并列出根目录。"""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(400, "请粘贴分享链接")
    sess = parse_share_link(text)
    if not sess:
        raise HTTPException(400, "无法识别的分享链接（支持夸克/UC/迅雷/百度/139/123/115/光鸭/蓝奏）")
    if sess.platform not in accounts.CLIENT_CLASSES:
        raise HTTPException(400,
                            f"{platform_label(sess.platform)}将在后续批次接入，当前已支持："
                            + "、".join(platform_label(k) for k in accounts.CLIENT_CLASSES))
    if req.passcode.strip():
        sess.passcode = req.passcode.strip()
    probe_client = await accounts.get_client(sess.platform)
    guest = not (probe_client and probe_client.cookie)
    try:
        session, client = await resolver.resolve_share(sess.platform, sess.share_id, sess.passcode)
        files = await resolver.list_dir(sess.platform, sess.share_id, sess.passcode, "0")
    except PanError as e:
        # 仅当「未登录」确实是失败主因时才附登录提示：
        # 平台本就要求登录，或错误信息指向登录态/取链受限
        msg = str(e)
        need_login_hint = guest and (
            not getattr(probe_client, "GUEST_SUPPORTED", False)
            or any(k in msg for k in ("登录", "需要对", "需要登", "游客", "提链", "token", "Cookie"))
        )
        hint = "；可在「设置 → 网盘账号」粘贴 Cookie 后重试" if need_login_hint else ""
        raise HTTPException(422, f"解析失败：{msg}{hint}")
    return {
        "code": 0,
        "session": {
            "platform": session.platform,
            "label": platform_label(session.platform),
            "share_id": session.share_id,
            "passcode": session.passcode,
            "title": session.title,
            "guest": guest,
            "notice": resolver.guest_notice(client) if guest else "",
        },
        "files": [_file_dict(f) for f in files],
    }


@router.post("/browse")
async def browse(req: BrowseRequest):
    if req.platform not in accounts.CLIENT_CLASSES:
        _unsupported(req.platform)
    try:
        files = await resolver.list_dir(req.platform, req.share_id, req.passcode, req.pdir_fid)
    except PanError as e:
        raise HTTPException(422, f"列目录失败：{e}")
    return {"code": 0, "files": [_file_dict(f, req.path) for f in files]}


# ---------- 直链签发 / 播放 / 下载 ----------

@router.post("/link")
async def issue_link(req: LinkRequest):
    """换取直链并签发 token：播放走 /stream/<token>，入库走 /download。"""
    if req.platform not in accounts.CLIENT_CLASSES:
        _unsupported(req.platform)
    try:
        sess, _ = await resolver.resolve_share(req.platform, req.share_id, req.passcode)
        files = await resolver.list_dir(req.platform, req.share_id, req.passcode, req.pdir_fid)
        target = next((f for f in files if f.fid == req.fid), None)
        if target is None:
            # 列表页信息可能过期（目录已翻页/移动）：退回全树定位
            target = await resolver.find_by_fid(req.platform, req.share_id, req.passcode, req.fid)
        if target is None:
            raise HTTPException(404, "文件不存在或分享已失效")
        link = await resolver.issue_link(req.platform, req.share_id, req.passcode, target)
    except PanError as e:
        raise HTTPException(422, f"取直链失败：{e}")
    return {
        "code": 0, "token": link.token, "name": link.filename, "size": link.size,
        "stream_path": f"/api/pan/stream/{link.token}",
        "playable": _is_browser_playable(link.filename),
    }


@router.get("/info/{token}")
async def link_info(token: str):
    link = resolver.take_link(token)
    if not link:
        raise HTTPException(410, "链接已过期，请重新获取")
    return {"code": 0, "name": link.filename, "size": link.size,
            "playable": _is_browser_playable(link.filename)}


@router.api_route("/stream/{token}", methods=["GET", "HEAD"])
async def stream(token: str, request: Request):
    """Range 透传播放代理：上游 = 签发时保存的直链 + 绑定请求头（含 Cookie）。

    直链签名与取链时刻 Cookie 绑定：上游 302/403 一律视为失效，绝不跟随重定向。
    """
    link = resolver.take_link(token)
    if not link:
        raise HTTPException(410, "链接已过期，请重新获取")

    upstream_headers = dict(link.headers or {})
    rng = request.headers.get("range")
    if rng:
        upstream_headers["Range"] = rng

    ctype = (mimetypes.guess_type(link.filename)[0] or "application/octet-stream")
    total = link.size

    if request.method == "HEAD":
        # 只回应答头，不拉流（播放器初始化探测）
        resp_headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-store"}
        status = 200
        if rng and total:
            m = re.match(r"bytes=(\d*)-(\d*)", rng.strip())
            if m:
                start = int(m.group(1) or 0)
                end = min(int(m.group(2)) if m.group(2) else total - 1, total - 1)
                if start > end:
                    raise HTTPException(416, "Range 越界")
                resp_headers["Content-Range"] = f"bytes {start}-{end}/{total}"
                resp_headers["Content-Length"] = str(end - start + 1)
                status = 206
        elif total:
            resp_headers["Content-Length"] = str(total)
        from fastapi.responses import Response
        return Response(status_code=status, headers=resp_headers, media_type=ctype)

    kwargs = {}
    proxy = get_proxy_with_detect()
    if proxy:
        kwargs["proxy"] = proxy
    client = httpx.AsyncClient(follow_redirects=False, verify=False,
                               timeout=httpx.Timeout(30.0, read=120.0), **kwargs)

    # 先建立上游流确认真实状态码，再决定响应头（头一旦发出就无法回退报错）
    req = client.build_request("GET", link.url, headers=upstream_headers)
    try:
        upstream = await client.send(req, stream=True)
    except httpx.HTTPError as e:
        await client.aclose()
        raise HTTPException(502, f"上游连接失败: {str(e)[:100]}")

    if upstream.status_code in (301, 302, 303, 307, 308):
        await upstream.aclose(); await client.aclose()
        raise HTTPException(410, "直链被重定向（Cookie/签名已失效），请重新播放")
    if upstream.status_code == 403:
        await upstream.aclose(); await client.aclose()
        raise HTTPException(403, "直链凭证已失效（Cookie/签名过期），请重新播放")
    if upstream.status_code not in (200, 206):
        await upstream.aclose(); await client.aclose()
        raise HTTPException(502, f"上游返回 HTTP {upstream.status_code}")

    resp_headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-store"}
    status = upstream.status_code
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

    return StreamingResponse(body(), media_type=ctype, status_code=status, headers=resp_headers)


@router.post("/download")
async def download(req: DownloadRequest):
    """签发文件排入统一下载引擎（分片并发 + .part 断点 + 完成自动进本地片库）。"""
    link = resolver.take_link(req.token)
    if not link:
        raise HTTPException(410, "链接已过期，请重新获取")
    folder = (req.folder or get_download_dir()).strip()
    task_id = await manager.add(
        source="pan", name=link.filename, url=link.url, folder=folder,
        headers=link.headers, filename=link.filename,
        extra={"platform": link.platform, "share_id": link.share_id, "fid": link.fid},
    )
    return {"code": 0, "id": task_id, "name": link.filename, "size": link.size}


# ---------- 账号管理 ----------

@router.get("/accounts")
async def list_accounts():
    return {"code": 0, "data": await accounts.list_accounts()}


@router.post("/accounts")
async def save_account(req: AccountRequest):
    if req.platform not in accounts.CLIENT_CLASSES:
        _unsupported(req.platform)
    cookie = req.cookie.strip()
    if not cookie:
        raise HTTPException(400, "Cookie 不能为空")
    try:
        info = await accounts.save_account(req.platform, cookie)
    except Exception as e:
        raise HTTPException(422, f"保存失败：Cookie 格式不符或网络错误（{str(e)[:120]}）")
    if not info["valid"]:
        return {"code": 1, "detail": "Cookie 已保存，但登录态校验未通过（关键字段缺失或已失效）",
                "data": info}
    return {"code": 0, "data": info}


@router.delete("/accounts/{platform}")
async def delete_account(platform: str):
    if platform not in accounts.CLIENT_CLASSES:
        _unsupported(platform)
    await accounts.delete_account(platform)
    return {"code": 0}


@router.post("/accounts/{platform}/check")
async def check_account(platform: str):
    if platform not in accounts.CLIENT_CLASSES:
        _unsupported(platform)
    return {"code": 0, "data": await accounts.check_account(platform)}


_PLAYABLE_EXT = {"mp4", "m4v", "webm", "mov"}


def _is_browser_playable(name: str) -> bool:
    """浏览器 <video> 能原生解的容器；mkv/ts 等标注需下载后本地播（tdl-web 同款提示）。"""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext in _PLAYABLE_EXT
