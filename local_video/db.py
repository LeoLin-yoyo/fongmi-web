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
    sort_order INTEGER NOT NULL DEFAULT 0,
    visible INTEGER NOT NULL DEFAULT 1,
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

CREATE TABLE IF NOT EXISTS dir_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS dir_group_items (
    group_id INTEGER NOT NULL,
    dir_id INTEGER NOT NULL,
    PRIMARY KEY (group_id, dir_id)
);
"""


class Database:
    def __init__(self, db_path: str | None = None):
        ensure_dirs()
        self._path = str(db_path or DB_PATH)
        self._lock = threading.RLock()
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """旧库升级：dirs 表补 sort_order / visible 列。"""
        cols = {r[1] for r in conn.execute("PRAGMA table_info(dirs)").fetchall()}
        if "sort_order" not in cols:
            conn.execute("ALTER TABLE dirs ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
        if "visible" not in cols:
            conn.execute("ALTER TABLE dirs ADD COLUMN visible INTEGER NOT NULL DEFAULT 1")

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
                "FROM dirs d ORDER BY d.sort_order, d.id"
            ).fetchall()
        return [dict(r) for r in rows]

    def add_dir(self, path: str) -> dict | None:
        path = path.strip().rstrip("\\/")
        with self._lock, self._connect() as conn:
            existing = conn.execute("SELECT * FROM dirs WHERE path = ?", (path,)).fetchone()
            if existing:
                return dict(existing)
            name = path.replace("/", "\\").rsplit("\\", 1)[-1] or path
            cur = conn.execute(
                "INSERT INTO dirs (path, name, sort_order) VALUES (?, ?, "
                "(SELECT COALESCE(MAX(sort_order), 0) + 1 FROM dirs))",
                (path, name),
            )
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
            conn.execute("DELETE FROM dir_group_items WHERE dir_id = ?", (dir_id,))
            conn.execute("DELETE FROM dirs WHERE id = ?", (dir_id,))
        return True

    def reorder_dirs(self, ordered_ids: list[int]) -> bool:
        """按传入顺序重排目录；ids 必须与现有目录一一对应才生效。"""
        with self._lock, self._connect() as conn:
            existing = [r["id"] for r in conn.execute("SELECT id FROM dirs").fetchall()]
            if sorted(ordered_ids) != sorted(existing):
                return False
            for idx, dir_id in enumerate(ordered_ids):
                conn.execute("UPDATE dirs SET sort_order = ? WHERE id = ?", (idx, dir_id))
        return True

    def set_dir_visible(self, dir_id: int, visible: bool) -> dict | None:
        """设置目录是否在片库页选项卡中显示（不影响扫描与聚合）。"""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE dirs SET visible = ? WHERE id = ?", (1 if visible else 0, dir_id)
            )
            if cur.rowcount == 0:
                return None
        return self.get_dir(dir_id)

    # ---- 聚合选项卡（目录组） ----

    def _valid_dir_ids(self, conn: sqlite3.Connection, dir_ids: list[int]) -> bool:
        if not dir_ids:
            return False
        marks = ",".join("?" for _ in dir_ids)
        rows = conn.execute(f"SELECT id FROM dirs WHERE id IN ({marks})", dir_ids).fetchall()
        return len(rows) == len(set(dir_ids))

    def _set_group_items(self, conn: sqlite3.Connection, group_id: int, dir_ids: list[int]) -> None:
        conn.execute("DELETE FROM dir_group_items WHERE group_id = ?", (group_id,))
        conn.executemany(
            "INSERT OR IGNORE INTO dir_group_items (group_id, dir_id) VALUES (?, ?)",
            [(group_id, d) for d in dict.fromkeys(dir_ids)],
        )

    def list_groups(self) -> list[dict]:
        with self._lock, self._connect() as conn:
            groups = conn.execute("SELECT * FROM dir_groups ORDER BY id").fetchall()
            items = conn.execute("SELECT group_id, dir_id FROM dir_group_items").fetchall()
        by_group: dict[int, list[int]] = {}
        for it in items:
            by_group.setdefault(it["group_id"], []).append(it["dir_id"])
        return [{**dict(g), "dir_ids": by_group.get(g["id"], [])} for g in groups]

    def create_group(self, name: str, dir_ids: list[int]) -> dict | None:
        name = name.strip()
        with self._lock, self._connect() as conn:
            if not name or not self._valid_dir_ids(conn, dir_ids):
                return None
            cur = conn.execute("INSERT INTO dir_groups (name) VALUES (?)", (name,))
            group_id = cur.lastrowid
            self._set_group_items(conn, group_id, dir_ids)
        return self.get_group(group_id)

    def update_group(self, group_id: int, name: str, dir_ids: list[int]) -> dict | None:
        name = name.strip()
        with self._lock, self._connect() as conn:
            if not conn.execute("SELECT id FROM dir_groups WHERE id = ?", (group_id,)).fetchone():
                return None
            if not name or not self._valid_dir_ids(conn, dir_ids):
                return None
            conn.execute("UPDATE dir_groups SET name = ? WHERE id = ?", (name, group_id))
            self._set_group_items(conn, group_id, dir_ids)
        return self.get_group(group_id)

    def delete_group(self, group_id: int) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM dir_groups WHERE id = ?", (group_id,))
            conn.execute("DELETE FROM dir_group_items WHERE group_id = ?", (group_id,))
        return cur.rowcount > 0

    def get_group(self, group_id: int) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM dir_groups WHERE id = ?", (group_id,)).fetchone()
            if not row:
                return None
            items = conn.execute(
                "SELECT dir_id FROM dir_group_items WHERE group_id = ? ORDER BY dir_id",
                (group_id,),
            ).fetchall()
        return {**dict(row), "dir_ids": [r["dir_id"] for r in items]}

    def get_group_dir_paths(self, group_id: int) -> list[str]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT d.path FROM dir_group_items gi JOIN dirs d ON d.id = gi.dir_id "
                "WHERE gi.group_id = ?",
                (group_id,),
            ).fetchall()
        return [r["path"] for r in rows]

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
        group_id: int | None = None,
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
        if group_id is not None:
            paths = self.get_group_dir_paths(group_id)
            if paths:
                marks = ",".join("?" for _ in paths)
                where.append(f"v.dir_path IN ({marks})")
                params.extend(paths)
            else:
                where.append("0 = 1")
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

    def count_videos(self, search: str = "", dir_id: int | None = None, group_id: int | None = None) -> int:
        where, params = [], []
        if search:
            where.append("name LIKE ?")
            params.append(f"%{search}%")
        if dir_id is not None:
            sub = self.get_dir(dir_id)
            where.append("dir_path = ?")
            params.append(sub["path"] if sub else "__none__")
        if group_id is not None:
            paths = self.get_group_dir_paths(group_id)
            if paths:
                marks = ",".join("?" for _ in paths)
                where.append(f"dir_path IN ({marks})")
                params.extend(paths)
            else:
                where.append("0 = 1")
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
