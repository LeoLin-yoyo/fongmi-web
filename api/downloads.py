"""统一下载任务 REST API（挂载于 /api/downloads）。

- CRUD + 暂停/继续/取消，进度经 SSE 实时推送（event: task / task-progress / tasks-changed）
- 下载目录为全局设置（data/config.json 的 download_dir），用户可自定义绝对路径
"""
import asyncio
import json
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from spider.proxy_config import set_config_value

from downloader.config import DEFAULT_DOWNLOAD_DIR, get_download_dir
from downloader.tasks import manager

router = APIRouter(prefix="/downloads", tags=["downloads"])


class TaskCreate(BaseModel):
    url: str
    name: str = ""
    filename: str = ""
    folder: str = ""
    headers: dict | None = None
    source: str = "url"
    block: int = 0
    connections: int = 0
    extra: dict | None = None


class DirUpdate(BaseModel):
    dir: str


@router.get("/tasks")
async def list_tasks():
    return {"code": 0, "data": await manager.list()}


@router.post("/tasks")
async def create_task(body: TaskCreate):
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "仅支持 http/https 直链")
    folder = (body.folder or get_download_dir()).strip()
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError as e:
        raise HTTPException(400, f"下载目录不可用: {e}")
    task_id = await manager.add(
        source=body.source, name=body.name or body.filename, url=url,
        folder=folder, headers=body.headers, filename=body.filename,
        block=body.block, connections=body.connections, extra=body.extra,
    )
    return {"code": 0, "id": task_id}


@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: int):
    ok = await manager.pause(task_id)
    return {"code": 0, "ok": ok}


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: int):
    ok = await manager.resume(task_id)
    if not ok:
        raise HTTPException(400, "任务不存在或当前状态不可继续")
    return {"code": 0, "ok": ok}


@router.delete("/tasks/{task_id}")
async def cancel_task(task_id: int, remove_files: bool = False):
    ok = await manager.cancel(task_id, remove_files=remove_files)
    if not ok:
        raise HTTPException(404, "任务不存在")
    return {"code": 0}


@router.delete("/tasks/{task_id}/record")
async def delete_record(task_id: int):
    """仅移除任务记录（运行中的任务不会被删除）。"""
    items = await manager.list()
    for it in items:
        if it["id"] == task_id and it["status"] in ("running", "queued"):
            raise HTTPException(400, "任务进行中，请先取消")
    ok = await manager.delete(task_id)
    return {"code": 0, "ok": ok}


@router.get("/config")
async def download_config():
    return {"code": 0, "dir": get_download_dir(), "default_dir": DEFAULT_DOWNLOAD_DIR}


@router.post("/config")
async def update_download_config(body: DirUpdate):
    d = body.dir.strip()
    if d:
        if not os.path.isabs(d):
            raise HTTPException(400, "请填写绝对路径")
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".fongmi_write_test")
            fd = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.close(fd)
            os.unlink(probe)
        except OSError as e:
            raise HTTPException(400, f"目录不可写: {e}")
    set_config_value("download_dir", d)
    return {"code": 0, "dir": get_download_dir()}


@router.get("/events")
async def events(request: Request):
    """SSE：任务进度与状态变化实时推送。"""
    queue = manager.subscribe()

    async def stream():
        try:
            yield "event: hello\ndata: {}\n\n"
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=20)
                    yield f"event: {item['event']}\ndata: {json.dumps(item['data'], ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                if await request.is_disconnected():
                    break
        finally:
            manager.unsubscribe(queue)

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
