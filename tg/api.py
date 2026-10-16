"""Telegram REST API（挂载于 /api/tg）。

安全口径（继承 tdl-web 的教训）：
- 只接受 t.me 链接，交给 tdl 的字符串由服务端用硬编码 host 重新构造
- 播放/下载字节流都经服务端内部 loopback 的 serve 进程，不暴露任意外部 URL
- serve 端口由 sid 派生，path 只接受数字对
"""
import asyncio
import os
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from downloader import manager as dl_manager
from downloader.config import get_download_dir

from . import tdlfetch
from .config import get_config, save_config
from .link import extract_links, parse_tg_link, sanitize_link
from .login import login_manager
from .serve import serve_manager
from .session import invalidate, list_chats
from .stream import drop_streamers, get_streamer, parse_range

router = APIRouter(prefix="/tg", tags=["tg"])

# 播放会话：sid → {urls, files}
_play_sessions: dict[str, dict] = {}
_cur_play: dict = {"sid": ""}


class PreviewRequest(BaseModel):
    urls: str           # 一行或多行 t.me 链接


class InputRequest(BaseModel):
    value: str


class LoginRequest(BaseModel):
    kind: str = "qr"    # qr / code
    phone: str = ""
    ns: str = ""


class TgDownloadRequest(BaseModel):
    sid: str
    href: str
    name: str = ""
    folder: str = ""


# ---------- 配置 ----------

@router.get("/config")
async def get_tg_config():
    cfg = get_config()
    return {"code": 0, "data": cfg.__dict__, "tdl": tdlfetch.status(),
            "login": login_manager.status(), "sessions": serve_manager.list()}


@router.post("/config")
async def update_tg_config(body: dict):
    cfg = save_config(body or {})
    return {"code": 0, "data": cfg.__dict__, "tdl": tdlfetch.status()}


@router.get("/tdl/status")
async def tdl_status():
    return {"code": 0, "data": tdlfetch.status()}


@router.post("/tdl/download")
async def tdl_download():
    async def _go():
        try:
            info = await tdlfetch.download_latest()
            # 下载后刷新 runner 路径发现
            from .runner import runner
            cfg = get_config()
            runner.locate(info.get("path") or cfg.tdl_path)
            return {"code": 0, "data": info}
        except Exception as e:
            raise HTTPException(422, f"下载 tdl 失败：{str(e)[:160]}")
    return await _go()


# ---------- 登录 ----------

@router.get("/login")
async def login_status():
    return {"code": 0, "data": login_manager.status()}


@router.post("/login/detect")
async def login_detect():
    state = await login_manager.detect_async()
    return {"code": 0, "state": state}


@router.post("/login/start")
async def login_start(req: LoginRequest):
    if req.kind not in ("qr", "code"):
        raise HTTPException(400, "kind 必须是 qr 或 code")
    if req.kind == "code" and not req.phone.strip():
        raise HTTPException(400, "手机号登录需要填写手机号")
    sess = await login_manager.start(req.kind, req.phone, req.ns)
    return {"code": 0, "data": sess.public()}


@router.post("/login/input")
async def login_input(req: InputRequest):
    ok = login_manager.submit_input(req.value)
    if not ok:
        raise HTTPException(400, "当前状态不接受输入")
    return {"code": 0}


@router.post("/login/cancel")
async def login_cancel():
    await login_manager.cancel()
    return {"code": 0}


@router.get("/chats")
async def chats(refresh: bool = False):
    try:
        data = await list_chats(refresh=refresh)
    except Exception as e:
        return {"code": 1, "detail": str(e)[:160], "data": []}
    return {"code": 0, "data": data}


# ---------- 解析/预览 ----------

@router.post("/preview")
async def preview(req: PreviewRequest):
    """粘贴链接 → 起 tdl serve 会话 → 返回文件清单。"""
    links = extract_links(req.urls or "")
    if not links:
        raise HTTPException(400, "未识别到有效的 t.me 链接")
    cfg = get_config()
    out_dir = cfg.download_dir or get_download_dir()
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as e:
        raise HTTPException(400, f"下载目录不可用: {e}")

    # 替换上一个播放会话
    if _cur_play.get("sid"):
        await serve_manager.stop(_cur_play["sid"])
        drop_streamers(_cur_play["sid"])

    try:
        sess = await serve_manager.start(links, out_dir)
    except Exception as e:
        raise HTTPException(422, f"解析失败：{str(e)[:160]}")
    if sess.state != "ready":
        raise HTTPException(422, sess.error or "tdl serve 启动失败")

    _play_sessions[sess.sid] = {"urls": links, "files": sess.files}
    _cur_play["sid"] = sess.sid
    return {"code": 0, "data": {"sid": sess.sid, "dir": out_dir, "files": sess.files}}


@router.get("/session/{sid}")
async def session_state(sid: str):
    sess = serve_manager.get(sid)
    if not sess:
        raise HTTPException(404, "会话不存在或已关闭")
    return {"code": 0, "data": {"sid": sid, "state": sess.state, "files": sess.files}}


@router.post("/session/{sid}/stop")
async def stop_session(sid: str):
    await serve_manager.stop(sid)
    drop_streamers(sid)
    _play_sessions.pop(sid, None)
    if _cur_play.get("sid") == sid:
        _cur_play["sid"] = ""
    return {"code": 0}


# ---------- 播放流代理 ----------

@router.api_route("/stream/{sid}/{href:path}", methods=["GET", "HEAD"])
async def stream(sid: str, href: str, request: Request):
    sess = serve_manager.get(sid)
    if not sess or sess.state != "ready":
        raise HTTPException(404, "会话不存在或未就绪")
    from .serve import parse_href, mime_of
    pair = parse_href(href)
    if not pair:
        raise HTTPException(400, "非法文件引用")
    file = next((f for f in sess.files if f["href"] == href), None)
    if not file:
        raise HTTPException(404, "文件不存在")
    total = file["size"]
    ctype = mime_of(file["name"])
    sess.touch()

    if request.method == "HEAD":
        return StreamingResponse(
            iter(()), media_type=ctype,
            headers={"Accept-Ranges": "bytes", "Content-Length": str(total)})

    rng = parse_range(request.headers.get("range"), total)
    if rng is None:
        start, end = 0, total - 1
        status = 200
    else:
        start, end = rng
        status = 206

    st = get_streamer(sess, href, total)
    headers = {
        "Accept-Ranges": "bytes", "Cache-Control": "no-store",
        "Content-Length": str(end - start + 1),
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"

    return StreamingResponse(st.iter_range(start, end), status_code=status,
                             media_type=ctype, headers=headers)


@router.get("/stats/{sid}/{href:path}")
async def stream_stats(sid: str, href: str):
    sess = serve_manager.get(sid)
    if not sess:
        raise HTTPException(404, "会话不存在")
    file = next((f for f in sess.files if f["href"] == href), None)
    if not file:
        raise HTTPException(404, "文件不存在")
    st = get_streamer(sess, href, file["size"])
    return {"code": 0, "data": st.stats()}


@router.post("/download")
async def tg_download(req: TgDownloadRequest):
    """在线播放的文件加入下载队列（走统一下载引擎，从 serve 拉字节）。

    为保持断点续传语义，这里把 serve 的该文件 URL 作为直链交给下载引擎；
    serve 仅绑 127.0.0.1，引擎同机访问。
    """
    sess = serve_manager.get(req.sid)
    if not sess:
        raise HTTPException(404, "会话不存在或已关闭")
    from .serve import parse_href
    if not parse_href(req.href):
        raise HTTPException(400, "非法文件引用")
    file = next((f for f in sess.files if f["href"] == req.href), None)
    if not file:
        raise HTTPException(404, "文件不存在")
    # 目录优先级：请求指定 → TG 设置 → 全局下载目录
    folder = (req.folder or get_config().download_dir or get_download_dir()).strip()
    task_id = await dl_manager.add(
        source="tg", name=req.name or file["name"],
        url=f"{sess.base}/{req.href}", folder=folder,
        filename=req.name or file["name"],
        extra={"tg_sid": req.sid, "href": req.href},
    )
    return {"code": 0, "id": task_id, "name": req.name or file["name"]}


@router.get("/playable/{sid}")
async def playable(sid: str):
    """会话内可浏览器直接播放的文件（mp4/webm…）。"""
    sess = serve_manager.get(sid)
    if not sess:
        raise HTTPException(404, "会话不存在")
    return {"code": 0, "data": [f for f in sess.files if f["playable"]]}
