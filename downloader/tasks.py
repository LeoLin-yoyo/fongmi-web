"""下载任务管理器：状态机、速度统计、事件推送、完成后并入本地片库。

任务状态机（对齐 tdl-web tasks.js 口径）：
    queued → running → success
    running → paused → queued(续传)
    running → failed / canceled / interrupted（带断点，可续传）
"""
import asyncio
import json
import os
import time
from datetime import datetime

import httpx
from loguru import logger
from sqlalchemy import desc, select, update

from model.database import DownloadTask as TaskRow
from model.database import async_session
from spider.proxy_config import get_proxy_with_detect

from . import engine, journal
from .engine import (
    DownloadError,
    FatalDownloadError,
    FileDownloader,
    PauseRequested,
    ServeDeadError,
)

MAX_CONCURRENT_TASKS = 2  # 同时运行的文件任务数（分片并发在任务内部）


class TaskManager:
    def __init__(self):
        self._runtime: dict[int, dict] = {}
        self._queue: asyncio.Queue | None = None
        self._worker: asyncio.Task | None = None
        self._listeners: set[asyncio.Queue] = set()
        self._last_emit: dict[int, float] = {}

    # ---------- 生命周期 ----------
    def start(self):
        if self._worker is None or self._worker.done():
            self._queue = asyncio.Queue()
            self._worker = asyncio.create_task(self._loop())
            asyncio.create_task(self._recover_orphans())
        # 重启后把中断态任务重新排队自动续传（断点保留）
        asyncio.create_task(self._requeue_interrupted())

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._listeners.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._listeners.discard(q)

    def _emit(self, event: str, payload: dict):
        for q in list(self._listeners):
            try:
                q.put_nowait({"event": event, "data": payload})
            except asyncio.QueueFull:
                pass

    def _fresh_runtime(self) -> dict:
        return {"status": "queued", "done": 0, "total": 0, "speed": 0,
                "paused": asyncio.Event(), "canceled": asyncio.Event(), "handle": None}

    # ---------- CRUD ----------
    async def add(self, *, source: str, name: str, url: str, folder: str,
                  headers: dict | None = None, filename: str = "",
                  block: int = 0, connections: int = 0, extra: dict | None = None) -> int:
        async with async_session() as session:
            row = TaskRow(
                source=source, name=name or filename, url=url, folder=folder,
                headers=json.dumps(headers or {}, ensure_ascii=False),
                filename=filename, block=block, connections=connections,
                extra=json.dumps(extra or {}, ensure_ascii=False),
                status="queued",
            )
            session.add(row)
            await session.commit()
            task_id = row.id
        self._runtime[task_id] = self._fresh_runtime()
        self._queue.put_nowait(task_id)
        await self._push(task_id)
        return task_id

    async def pause(self, task_id: int) -> bool:
        rt = self._runtime.get(task_id)
        if rt and rt["status"] == "running":
            # 协作式暂停：引擎在块边界/分片到达时检查事件并保存断点
            rt["paused"].set()
            return True
        if rt and rt["status"] == "queued":
            await self._set_status(task_id, "paused", "paused")
            return True
        return False

    async def resume(self, task_id: int) -> bool:
        async with async_session() as session:
            row = await session.get(TaskRow, task_id)
            if not row or row.status not in ("paused", "failed", "canceled", "interrupted"):
                return False
            row.status = "queued"
            row.error = ""
            await session.commit()
        self._runtime[task_id] = self._fresh_runtime()
        self._queue.put_nowait(task_id)
        await self._push(task_id)
        return True

    async def cancel(self, task_id: int, remove_files: bool = False) -> bool:
        rt = self._runtime.get(task_id)
        if rt:
            rt["canceled"].set()
            rt["paused"].set()
        async with async_session() as session:
            row = await session.get(TaskRow, task_id)
            if not row:
                return False
            if row.status != "success":
                row.status = "canceled"
            if remove_files and row.file_path:
                for p in (row.file_path, journal.part_path(row.file_path), journal.meta_path(row.file_path)):
                    try:
                        if os.path.isfile(p):
                            os.unlink(p)
                    except OSError:
                        pass
            await session.commit()
        await self._push(task_id)
        return True

    async def delete(self, task_id: int) -> bool:
        await self.cancel(task_id)
        async with async_session() as session:
            row = await session.get(TaskRow, task_id)
            if not row:
                return False
            await session.delete(row)
            await session.commit()
        self._runtime.pop(task_id, None)
        self._emit("task", {"id": task_id, "deleted": True})
        return True

    async def list(self) -> list[dict]:
        async with async_session() as session:
            rows = (await session.execute(
                select(TaskRow).order_by(desc(TaskRow.id)).limit(300)
            )).scalars().all()
        out = []
        for r in rows:
            rt = self._runtime.get(r.id, {})
            done = rt.get("done", 0) or r.done
            total = rt.get("total", 0) or r.size
            speed = rt.get("speed", 0)
            status = rt.get("status") or r.status
            if r.status in ("success", "canceled"):
                status = r.status
            out.append({
                "id": r.id, "source": r.source, "name": r.name, "status": status,
                "file_path": r.file_path, "error": r.error,
                "done": done, "total": total, "speed": speed,
                "pct": round(done * 100 / total, 1) if total else 0.0,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            })
        return out

    async def _row_dict(self, task_id: int) -> dict | None:
        for it in await self.list():
            if it["id"] == task_id:
                return it
        return None

    async def _push(self, task_id: int):
        snap = await self._row_dict(task_id)
        if snap:
            self._emit("task", snap)

    async def _set_status(self, task_id: int, rt_status: str, db_status: str = "", error: str = ""):
        rt = self._runtime.get(task_id)
        if rt:
            rt["status"] = rt_status
            if rt_status != "running":
                rt["speed"] = 0
        async with async_session() as session:
            row = await session.get(TaskRow, task_id)
            if not row:
                return
            row.status = db_status or rt_status
            row.error = (error or "")[:2000]
            if db_status in ("success", "failed", "canceled", "interrupted"):
                row.finished_at = datetime.now()
            await session.commit()
        await self._push(task_id)

    # ---------- 执行 ----------
    async def _recover_orphans(self):
        """重启恢复：DB 中 running/queued 改写为 interrupted，稍后自动续传。"""
        try:
            async with async_session() as session:
                await session.execute(
                    update(TaskRow)
                    .where(TaskRow.status.in_(["running", "queued"]))
                    .values(status="interrupted")
                )
                await session.commit()
        except Exception as e:
            logger.error(f"下载任务孤儿恢复失败: {e}")

    async def _requeue_interrupted(self):
        """自动续传重启前中断的任务（用户暂停的 paused 不自动续）。"""
        await asyncio.sleep(3)
        try:
            async with async_session() as session:
                rows = (await session.execute(
                    select(TaskRow).where(TaskRow.status == "interrupted")
                )).scalars().all()
            ids = [r.id for r in rows]
            for tid in ids:
                await self.resume(tid)
            if ids:
                logger.info(f"自动续传 {len(ids)} 个中断的下载任务")
        except Exception as e:
            logger.error(f"自动续传失败: {e}")

    async def _loop(self):
        sem = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
        while True:
            task_id = await self._queue.get()
            asyncio.create_task(self._run_guarded(task_id, sem))

    async def _run_guarded(self, task_id: int, sem: asyncio.Semaphore):
        rt = self._runtime.setdefault(task_id, self._fresh_runtime())
        rt["handle"] = asyncio.current_task()
        async with sem:
            try:
                await self._run(task_id)
            except asyncio.CancelledError:
                if rt["canceled"].is_set():
                    await self._set_status(task_id, "canceled", "canceled")
                else:
                    await self._set_status(task_id, "paused", "paused")
            except Exception as e:
                logger.error(f"下载任务 {task_id} 异常: {e}")
                await self._set_status(task_id, "failed", "failed", str(e)[:500])
            finally:
                rt["handle"] = None

    async def _build_client(self, headers: dict) -> httpx.AsyncClient:
        kwargs = {}
        proxy = get_proxy_with_detect()
        if proxy:
            kwargs["proxy"] = proxy
        return httpx.AsyncClient(
            follow_redirects=False, verify=False,
            timeout=httpx.Timeout(30.0, read=180.0),
            limits=httpx.Limits(max_connections=128, max_keepalive_connections=64),
            **kwargs,
        )

    async def _run(self, task_id: int):
        async with async_session() as session:
            row = await session.get(TaskRow, task_id)
            if not row or row.status != "queued":
                return
            url, folder = row.url, row.folder
            headers = json.loads(row.headers or "{}")
            filename, block, connections = row.filename, row.block, row.connections

        rt = self._runtime.setdefault(task_id, self._fresh_runtime())
        rt["status"] = "running"
        rt["done"], rt["total"], rt["speed"] = row.done, row.size, 0
        await self._set_status(task_id, "running", "running")

        client = await self._build_client(headers)
        last_emit = [0.0, 0]

        def on_progress(done: int, total: int):
            rt["done"], rt["total"] = done, total
            now = time.monotonic()
            prev_t, prev_d = last_emit[0], last_emit[1]
            if prev_t and now - prev_t >= 1.0:
                inst = max(0, done - prev_d) / (now - prev_t)
                rt["speed"] = int(rt["speed"] * 0.4 + inst * 0.6)
            if not prev_t or now - prev_t >= 0.5:
                last_emit[0], last_emit[1] = now, done
                self._emit_progress(task_id)

        downloader = FileDownloader(
            client, url, folder, filename_hint=filename, headers=headers,
            block=block or 8 * 1024 * 1024, connections=connections or 8,
            on_progress=on_progress, stop_event=rt["paused"],
        )
        try:
            result = await downloader.run()
            await self._on_success(task_id, result, downloader.total)
        except PauseRequested:
            if rt["canceled"].is_set():
                await self._set_status(task_id, "canceled", "canceled")
            else:
                await self._set_status(task_id, "paused", "paused")
        except FatalDownloadError as e:
            await self._set_status(task_id, "failed", "failed", str(e))
        except ServeDeadError as e:
            await self._set_status(task_id, "interrupted", "interrupted",
                                   f"{e}（上游会话中断，进度已保存）")
        except DownloadError as e:
            await self._set_status(task_id, "failed", "failed", str(e)[:500])
        finally:
            await client.aclose()
            if rt["canceled"].is_set():
                self._runtime.pop(task_id, None)

    def _emit_progress(self, task_id: int):
        now = time.monotonic()
        if now - self._last_emit.get(task_id, 0) < 0.4:
            return
        self._last_emit[task_id] = now
        rt = self._runtime.get(task_id, {})
        self._emit("task-progress", {
            "id": task_id, "status": rt.get("status", ""),
            "done": rt.get("done", 0), "total": rt.get("total", 0),
            "speed": rt.get("speed", 0),
        })

    async def _on_success(self, task_id: int, final: str, total: int):
        async with async_session() as session:
            row = await session.get(TaskRow, task_id)
            if row:
                row.file_path = final
                row.size = total
                row.done = total
                row.status = "success"
                row.error = ""
                row.finished_at = datetime.now()
                await session.commit()
        rt = self._runtime.get(task_id)
        if rt:
            rt["status"] = "success"
            rt["speed"] = 0
            rt["done"] = total
        await self._push(task_id)
        # 自动并入本地片库（目标目录已被扫描管理时）
        try:
            await _index_into_local_library(final)
        except Exception as e:
            logger.debug(f"入库本地片库失败（不影响下载结果）: {e}")


async def _index_into_local_library(path: str):
    from local_video import probe as lv_probe
    from local_video.state import app_state

    if not app_state.db:
        return
    real = os.path.abspath(path)
    for d in app_state.db.list_dirs():
        root = os.path.abspath(d["path"])
        if real == root or real.startswith(root + os.sep):
            try:
                meta = lv_probe.probe_video(path)
            except Exception:
                meta = {}
            app_state.db.upsert_video({
                "path": path,
                "name": os.path.basename(path),
                "dir_path": d["path"],
                "size": os.path.getsize(path),
                "duration": meta.get("duration"),
                "width": meta.get("width"),
                "height": meta.get("height"),
                "codec": meta.get("codec"),
                "container": os.path.splitext(path)[1].lower().lstrip("."),
                "mtime": os.path.getmtime(path),
                "has_thumb": 0,
            })
            row = app_state.db.get_video_by_path(path)
            if row:
                import threading
                threading.Thread(target=lv_probe.generate_thumbnail,
                                 args=(path, row["id"]), daemon=True).start()
            return


manager = TaskManager()


def init_downloader():
    """在 FastAPI lifespan 中调用（必须在事件循环内）。"""
    manager.start()
