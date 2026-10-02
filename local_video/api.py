"""REST API 路由（挂载于 /api/local）。"""
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import FileResponse

from .config import MEDIA_TYPES, THUMB_DIR
from .db import Database
from .probe import generate_thumbnail
from .scanner import Scanner

router = APIRouter(prefix="/local", tags=["local"])


def _get_db() -> Database:
    from .state import app_state
    return app_state.db


def _get_scanner() -> Scanner:
    from .state import app_state
    return app_state.scanner


@router.get("/dirs")
def list_dirs():
    return _get_db().list_dirs()


@router.post("/dirs")
def add_dir(body: dict):
    path = (body.get("path") or "").strip()
    if not path:
        raise HTTPException(400, "路径不能为空")
    db = _get_db()
    if not Path(path).is_dir():
        raise HTTPException(400, f"目录不存在: {path}")
    row = db.add_dir(path)
    if row is None:
        raise HTTPException(500, "添加目录失败")
    return row


@router.delete("/dirs/{dir_id}")
def delete_dir(dir_id: int):
    if not _get_db().delete_dir(dir_id):
        raise HTTPException(404, "目录不存在")
    return {"ok": True}


@router.post("/dirs/{dir_id}/scan")
def scan_dir(dir_id: int, background: BackgroundTasks):
    db = _get_db()
    row = db.get_dir(dir_id)
    if not row:
        raise HTTPException(404, "目录不存在")
    background.add_task(_get_scanner().scan_dir, row["path"])
    return {"ok": True, "message": "扫描已开始"}


@router.post("/scan")
def scan_all(background: BackgroundTasks):
    background.add_task(_get_scanner().scan_all)
    return {"ok": True, "message": "扫描已开始"}


@router.get("/scan/status")
def scan_status():
    return _get_scanner().status


@router.get("/videos")
def list_videos(
    search: str = "",
    dir_id: int | None = None,
    sort: str = Query("mtime", pattern="^(name|size|duration|created|mtime)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    db = _get_db()
    videos = db.list_videos(search=search, dir_id=dir_id, sort=sort, order=order, limit=limit, offset=offset)
    total = db.count_videos(search=search, dir_id=dir_id)
    return {"items": videos, "total": total, "limit": limit, "offset": offset}


@router.get("/videos/{video_id}")
def get_video(video_id: int):
    row = _get_db().get_video(video_id)
    if not row:
        raise HTTPException(404, "视频不存在")
    return row


@router.delete("/videos")
def delete_videos(ids: str = Query(...)):
    """批量物理删除视频：删除磁盘文件 + 数据库记录 + 缩略图缓存。"""
    id_list = []
    for part in ids.split(","):
        part = part.strip()
        if part.isdigit():
            id_list.append(int(part))
    if not id_list:
        raise HTTPException(400, "请提供要删除的视频 ID")
    db = _get_db()
    deleted, missing = 0, 0
    for vid_id in id_list:
        row = db.get_video(vid_id)
        if not row:
            continue
        p = Path(row["path"])
        try:
            if p.is_file():
                p.unlink()
                deleted += 1
            else:
                missing += 1
        except OSError as e:
            raise HTTPException(500, f"删除文件失败: {p.name}: {e}")
        db.delete_video(vid_id)
        thumb = THUMB_DIR / f"{vid_id}.jpg"
        if thumb.exists():
            try:
                thumb.unlink()
            except OSError:
                pass
    return {"ok": True, "deleted": deleted, "missing": missing}


@router.get("/videos/{video_id}/stream")
def stream_video(video_id: int, request: Request):
    row = _get_db().get_video(video_id)
    if not row:
        raise HTTPException(404, "视频不存在")
    file_path = Path(row["path"])
    if not file_path.is_file():
        raise HTTPException(404, "视频文件已被移动或删除")
    media_type = MEDIA_TYPES.get(file_path.suffix.lower(), "application/octet-stream")
    return stream_file_response(file_path, media_type, request.headers.get("range"))


@router.get("/videos/{video_id}/thumb")
def video_thumb(video_id: int):
    db = _get_db()
    row = db.get_video(video_id)
    if not row:
        raise HTTPException(404, "视频不存在")
    file_path = Path(row["path"])
    if not file_path.is_file():
        raise HTTPException(404, "视频文件已被移动或删除")
    thumb = generate_thumbnail(str(file_path), video_id)
    if thumb is None:
        raise HTTPException(404, "无法生成缩略图")
    db.mark_thumb(video_id)
    return FileResponse(thumb, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/stats")
def stats():
    return _get_db().stats()


def stream_file_response(file_path: Path, media_type: str, range_header: str | None):
    from .streaming import stream_video as _stream
    return _stream(file_path, media_type, range_header)
