"""ffprobe/ffmpeg 封装：元数据提取与缩略图生成。"""
import json
import subprocess
import threading
from pathlib import Path

from .config import THUMB_DIR

_thumb_semaphore = threading.Semaphore(2)


def probe_video(path: str) -> dict:
    """提取视频元数据，失败返回空 dict（调用方自行降级）。"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration:stream=codec_name,codec_type,width,height",
        "-of", "json",
        path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout or "{}")
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return {}

    meta = {"duration": None, "width": None, "height": None, "codec": None}
    try:
        dur = data.get("format", {}).get("duration")
        if dur:
            meta["duration"] = round(float(dur), 1)
    except (TypeError, ValueError):
        pass
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            meta["codec"] = stream.get("codec_name")
            w, h = stream.get("width"), stream.get("height")
            if w and h:
                meta["width"], meta["height"] = int(w), int(h)
            break
    return meta


def generate_thumbnail(video_path: str, video_id: int) -> Path | None:
    """抽取视频一帧生成缩略图并缓存，失败返回 None。"""
    thumb_path = THUMB_DIR / f"{video_id}.jpg"
    if thumb_path.exists():
        return thumb_path
    probe = probe_video(video_path)
    seek = "5"
    if probe.get("duration"):
        seek = str(max(1.0, probe["duration"] * 0.08))
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", seek,
        "-i", video_path,
        "-frames:v", "1",
        "-vf", "scale=480:-2",
        "-q:v", "4",
        str(thumb_path),
    ]
    with _thumb_semaphore:
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except (subprocess.SubprocessError, OSError):
            return None
    return thumb_path if thumb_path.exists() else None


def pregenerate_thumbnails(paths: list[tuple[str, int]]) -> None:
    """批量后台预生成缩略图（最多 2 并发）。"""
    for video_path, video_id in paths:
        generate_thumbnail(video_path, video_id)