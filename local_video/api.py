"""REST API 路由（挂载于 /api/local）。"""
import os
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import FileResponse

from spider.proxy_config import get_config_value

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


@router.put("/dirs/order")
def reorder_dirs(body: dict):
    """按传入 id 顺序重排媒体目录，顺序用于设置页列表与片库页筛选条。"""
    ids = body.get("ids")
    if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
        raise HTTPException(400, "ids 必须为目录 ID 数组")
    if not _get_db().reorder_dirs(ids):
        raise HTTPException(400, "目录 ID 列表与现有目录不一致")
    return {"ok": True, "dirs": _get_db().list_dirs()}


@router.patch("/dirs/{dir_id}/visible")
def set_dir_visible(dir_id: int, body: dict):
    """切换目录在片库页选项卡中的显示；隐藏不影响扫描与聚合。"""
    visible = body.get("visible")
    if not isinstance(visible, bool):
        raise HTTPException(400, "visible 必须为布尔值")
    row = _get_db().set_dir_visible(dir_id, visible)
    if row is None:
        raise HTTPException(404, "目录不存在")
    return row


@router.delete("/dirs/{dir_id}")
def delete_dir(dir_id: int):
    if not _get_db().delete_dir(dir_id):
        raise HTTPException(404, "目录不存在")
    return {"ok": True}


@router.get("/groups")
def list_groups():
    return _get_db().list_groups()


def _check_group_body(db: Database, body: dict) -> tuple[str, list[int]]:
    name = (body.get("name") or "").strip()
    dir_ids = body.get("dir_ids")
    if not name:
        raise HTTPException(400, "名称不能为空")
    if (
        not isinstance(dir_ids, list)
        or len(dir_ids) < 2
        or not all(isinstance(i, int) for i in dir_ids)
    ):
        raise HTTPException(400, "请至少选择 2 个目录")
    if len(set(dir_ids)) != len(dir_ids):
        raise HTTPException(400, "目录不能重复")
    for d in dir_ids:
        if not db.get_dir(d):
            raise HTTPException(400, f"目录不存在: {d}")
    return name, dir_ids


@router.post("/groups")
def create_group(body: dict):
    db = _get_db()
    name, dir_ids = _check_group_body(db, body)
    row = db.create_group(name, dir_ids)
    if row is None:
        raise HTTPException(500, "创建聚合选项卡失败")
    return row


@router.put("/groups/{group_id}")
def update_group(group_id: int, body: dict):
    db = _get_db()
    name, dir_ids = _check_group_body(db, body)
    row = db.update_group(group_id, name, dir_ids)
    if row is None:
        raise HTTPException(404, "聚合选项卡不存在")
    return row


@router.delete("/groups/{group_id}")
def delete_group(group_id: int):
    if not _get_db().delete_group(group_id):
        raise HTTPException(404, "聚合选项卡不存在")
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
    group_id: int | None = None,
    sort: str = Query("mtime", pattern="^(name|size|duration|created|mtime)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    if dir_id is not None and group_id is not None:
        raise HTTPException(400, "dir_id 与 group_id 不能同时使用")
    db = _get_db()
    videos = db.list_videos(search=search, dir_id=dir_id, group_id=group_id, sort=sort, order=order, limit=limit, offset=offset)
    total = db.count_videos(search=search, dir_id=dir_id, group_id=group_id)
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


@router.post("/videos/{video_id}/external-play")
def external_play(video_id: int):
    """用设置页配置的外部播放器（PotPlayer 等）打开本地视频文件。

    播放器路径持久化于 data/config.json。Windows 用 ShellExecuteW 启动
    （资源管理器双击同款 Shell 调用）：立即返回、播放器进程独立于后端、
    程序与参数分离传递，路径含空格/中文安全。
    """
    row = _get_db().get_video(video_id)
    if not row:
        raise HTTPException(404, "视频不存在")
    player = get_config_value("external_player_path").strip()
    if not player:
        raise HTTPException(400, "尚未配置外部播放器，请到「设置 → 本地视频」填写播放器路径")
    if not os.path.isfile(player):
        raise HTTPException(400, f"外部播放器路径不存在: {player}")
    video_path = Path(row["path"])
    if not video_path.is_file():
        raise HTTPException(404, "视频文件已被移动或删除")
    if os.name != "nt":
        raise HTTPException(500, "外部播放器功能目前仅支持 Windows")
    import ctypes
    SW_SHOWNORMAL = 1
    ret = ctypes.windll.shell32.ShellExecuteW(None, "open", player, f'"{video_path}"', None, SW_SHOWNORMAL)
    if ret <= 32:
        raise HTTPException(500, f"启动外部播放器失败（ShellExecute 错误码 {ret}）")
    return {"ok": True}


@router.get("/stats")
def stats():
    return _get_db().stats()


def stream_file_response(file_path: Path, media_type: str, range_header: str | None):
    from .streaming import stream_video as _stream
    return _stream(file_path, media_type, range_header)
