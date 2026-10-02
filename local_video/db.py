"""SQLite 数据访问层（线程安全）。"""
import sqlite3
import threading
from contextlib import contextmanager

from .config import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS dirs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    added_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    last_scan TEXT
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    dir_path TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    duration REAL,
    width INTEGER,
    height INTEGER,
    codec TEXT,
    container TEXT,
    mtime REAL NOT NULL DEFAULT 0,
    has_thumb INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_videos_dir ON videos(dir_path);
CREATE INDEX IF NOT EXISTS idx_videos_name ON videos(name);
"""


class Database:
    def __init__(self, db_path: str | None = None):
        ensure_dirs()
        self._path = str(db_path or DB_PATH)
        self._lock = threading.RLock()
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self._path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def list_dirs(self) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT d.*, (SELECT COUNT(*) FROM videos v WHERE v.dir_path = d.path) AS video_count "
                "FROM dirs d ORDER BY d.id"
            ).fetchall()
        return [dict(r) for r in rows]

    def add_dir(self, path: str) -> dict | None:
        path = path.strip().rstrip("\\/")
        with self._lock, self._connect() as conn:
            existing = conn.execute("SELECT * FROM dirs WHERE path = ?", (path,)).fetchone()
            if existing:
                return dict(existing)
            name = path.replace("/", "\\").rsplit("\\", 1)[-1] or path
            cur = conn.execute("INSERT INTO dirs (path, name) VALUES (?, ?)", (path, name))
            new_id = cur.lastrowid
        return self.get_dir(new_id)

    def get_dir(self, dir_id: int) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM dirs WHERE id = ?", (dir_id,)).fetchone()
        return dict(row) if row else None

    def delete_dir(self, dir_id: int) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("SELECT path FROM dirs WHERE id = ?", (dir_id,))
            row = cur.fetchone()
            if not row:
                return False
            conn.execute("DELETE FROM videos WHERE dir_path = ?", (row["path"],))
            conn.execute("DELETE FROM dirs WHERE id = ?", (dir_id,))
        return True

    def touch_scan(self, dir_id: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE dirs SET last_scan = datetime('now', 'localtime') WHERE id = ?",
                (dir_id,),
            )

    def upsert_video(self, video: dict) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO videos (path, name, dir_path, size, duration, width, height, codec, container, mtime, has_thumb)
                   VALUES (:path, :name, :dir_path, :size, :duration, :width, :height, :codec, :container, :mtime, :has_thumb)
                   ON CONFLICT(path) DO UPDATE SET
                     name=excluded.name, size=excluded.size, duration=excluded.duration,
                     width=excluded.width, height=excluded.height, codec=excluded.codec,
                     container=excluded.container, mtime=excluded.mtime, has_thumb=excluded.has_thumb""",
                video,
            )

    def get_video(self, video_id: int) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        return dict(row) if row else None

    def delete_video(self, video_id: int) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
        return cur.rowcount > 0

    def get_video_by_path(self, path: str) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM videos WHERE path = ?", (path,)).fetchone()
        return dict(row) if row else None

    def list_videos(
        self,
        search: str = "",
        dir_id: int | None = None,
        sort: str = "name",
        order: str = "asc",
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        where, params = [], []
        if search:
            where.append("v.name LIKE ?")
            params.append(f"%{search}%")
        if dir_id is not None:
            sub = self.get_dir(dir_id)
            where.append("v.dir_path = ?")
            params.append(sub["path"] if sub else "__none__")
        sql = "SELECT * FROM videos v"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sort_col = {"name": "v.name", "size": "v.size", "duration": "v.duration", "created": "v.created_at", "mtime": "v.mtime"}.get(sort, "v.mtime")
        sql += f" ORDER BY {sort_col} COLLATE NOCASE { 'DESC' if order == 'desc' else 'ASC' }"
        sql += " LIMIT ? OFFSET ?"
        params += [limit, offset]
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def count_videos(self, search: str = "", dir_id: int | None = None) -> int:
        where, params = [], []
        if search:
            where.append("name LIKE ?")
            params.append(f"%{search}%")
        if dir_id is not None:
            sub = self.get_dir(dir_id)
            where.append("dir_path = ?")
            params.append(sub["path"] if sub else "__none__")
        sql = "SELECT COUNT(*) AS c FROM videos"
        if where:
            sql += " WHERE " + " AND ".join(where)
        with self._lock, self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return row["c"]

    def all_video_paths(self) -> set[str]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT path FROM videos").fetchall()
        return {r["path"] for r in rows}

    def remove_missing(self, valid_paths: set[str], dir_path: str | None = None) -> int:
        with self._lock, self._connect() as conn:
            if dir_path:
                rows = conn.execute(
                    "SELECT id FROM videos WHERE dir_path = ?", (dir_path,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT id FROM videos").fetchall()
            removed = 0
            for r in rows:
                vid = conn.execute("SELECT path FROM videos WHERE id = ?", (r["id"],)).fetchone()
                if vid and vid["path"] not in valid_paths:
                    conn.execute("DELETE FROM videos WHERE id = ?", (r["id"],))
                    removed += 1
        return removed

    def mark_thumb(self, video_id: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE videos SET has_thumb = 1 WHERE id = ?", (video_id,))

    def stats(self) -> dict:
        with self._lock, self._connect() as conn:
            videos = conn.execute("SELECT COUNT(*) AS c FROM videos").fetchone()["c"]
            dirs = conn.execute("SELECT COUNT(*) AS c FROM dirs").fetchone()["c"]
            total_size = conn.execute(
                "SELECT COALESCE(SUM(size), 0) AS s FROM videos"
            ).fetchone()["s"]
        return {"video_count": videos, "dir_count": dirs, "total_size": total_size}
