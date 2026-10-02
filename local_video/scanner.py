"""后台目录扫描器：递归发现视频文件 + ffprobe 元数据 + 入库。"""
import logging
import threading
from pathlib import Path

from . import probe
from .config import VIDEO_EXTENSIONS
from .db import Database

logger = logging.getLogger(__name__)


class Scanner:
    def __init__(self, db: Database):
        self.db = db
        self._lock = threading.Lock()
        self._running = False
        self._progress = {"dir": None, "total": 0, "done": 0, "scanning": False}

    @property
    def status(self) -> dict:
        with self._lock:
            return dict(self._progress)

    def scan_all(self) -> None:
        dirs = self.db.list_dirs()
        for d in dirs:
            self.scan_dir(d["path"])

    def scan_dir(self, dir_path: str) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._progress = {"dir": dir_path, "total": 0, "done": 0, "scanning": True}
        try:
            self._do_scan(dir_path)
        finally:
            with self._lock:
                self._running = False
                self._progress["scanning"] = False

    def _do_scan(self, dir_path: str) -> None:
        root = Path(dir_path)
        if not root.is_dir():
            logger.warning("目录不存在，跳过: %s", dir_path)
            return

        files = [
            p for p in root.rglob("*")
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
        ]
        valid_paths: set[str] = set()
        with self._lock:
            self._progress["total"] = len(files)

        new_videos: list[tuple[str, int]] = []
        for i, file in enumerate(files, start=1):
            valid_paths.add(str(file))
            with self._lock:
                self._progress["done"] = i
            existing = self.db.get_video_by_path(str(file))
            if existing is not None and abs(existing["mtime"] - file.stat().st_mtime) < 0.001:
                continue
            record = self._build_record(file, dir_path)
            self.db.upsert_video(record)
            new_videos.append((str(file), self.db.get_video_by_path(str(file))["id"]))

        self.db.remove_missing(valid_paths, dir_path)
        dir_row = next((d for d in self.db.list_dirs() if d["path"] == dir_path), None)
        if dir_row:
            self.db.touch_scan(dir_row["id"])
        logger.info("扫描完成 %s: %d 个文件, %d 个新视频", dir_path, len(files), len(new_videos))

        if new_videos:
            t = threading.Thread(
                target=probe.pregenerate_thumbnails,
                args=(new_videos,),
                daemon=True,
                name=f"thumb-{Path(dir_path).name}",
            )
            t.start()

    @staticmethod
    def _build_record(file: Path, dir_path: str) -> dict:
        meta = probe.probe_video(str(file))
        return {
            "path": str(file),
            "name": file.name,
            "dir_path": dir_path,
            "size": file.stat().st_size,
            "duration": meta.get("duration"),
            "width": meta.get("width"),
            "height": meta.get("height"),
            "codec": meta.get("codec"),
            "container": file.suffix.lower().lstrip("."),
            "mtime": file.stat().st_mtime,
            "has_thumb": 0,
        }
