"""Range 分片并发下载引擎：probe → 预分配 .part → 块 worker 池 → 落盘改名。

与 journal.py 的 sidecar 格式配合实现块内断点续传；错误分类遵循
YunX §3.26 硬规则（403=凭证过期判失败、302=链接重定向失败、忽略 Range=致命）。
"""
import asyncio
import json
import os
import re
import time
import random
from pathlib import Path

import httpx
from loguru import logger

from . import journal

# 单块字节流内两次读取之间允许的最大空闲（tdl-web STALL_TIMEOUT 口径）
STALL_TIMEOUT = 20.0
BLOCK_RETRIES = 4
RETRY_BASE_MS = 400


class DownloadError(Exception):
    """下载失败（瞬时/致命细分由消息与类型决定）"""


class FatalDownloadError(DownloadError):
    """永久性失败：不支持 Range、403/416、协议错误——不消耗重试直接失败"""


class StallError(DownloadError):
    """链路假死：超过 STALL_TIMEOUT 无字节"""


class ServeDeadError(DownloadError):
    """上游 serve/直链进程已死：外层管理器自动重启会话后续传"""


class PauseRequested(Exception):
    """用户暂停：中止传输但保留 .part 与块内偏移"""


class CancelRequested(Exception):
    """用户取消：由调用方决定保留或删除半成品"""


_RANGE_RE = re.compile(r"bytes\s*=\s*(\d+)\s*-\s*(\d+)?", re.I)


def parse_content_range_total(text: str | None) -> int:
    """Content-Range: bytes 0-999/12345 → 12345"""
    if not text:
        return 0
    m = re.search(r"/(\d+)\s*$", text.strip())
    return int(m.group(1)) if m else 0


def filename_from_disposition(value: str | None) -> str:
    """Content-Disposition 文件名；latin1 错送 UTF-8 的还原（tdl serve 已知坑）。"""
    if not value:
        return ""
    m = re.search(r"filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)", value)
    if m:
        from urllib.parse import unquote
        return unquote(m.group(1).strip().strip('"'))
    m = re.search(r'filename\s*=\s*"([^"]+)"', value)
    if m:
        raw = m.group(1)
        try:
            fixed = raw.encode("latin-1").decode("utf-8")
            return fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            return raw
    return ""


def sanitize_filename(name: str) -> str:
    """跨平台文件名清洗（移植 YunX resolve_target 的字符/保留名部分）。"""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", (name or "").strip())
    name = name.rstrip(" .")
    if not name:
        return "download.bin"
    upper = name.upper().split(".")[0]
    bad = {"CON", "PRN", "AUX", "CLOCK$", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
    if upper in bad:
        name = "_" + name
    if len(name) > 200:
        stem, dot, ext = name.rpartition(".")
        if not dot or len(ext) > 12:
            stem, ext = name, ""
        keep = 200 - len(ext) - (1 if ext else 0)
        name = (stem[: max(1, keep)] + ("." + ext if ext else ""))
    return name


def resolve_target(folder: str, filename: str, size: int) -> str:
    """下载落盘路径解析：大小写不敏感碰撞 + 同尺寸复用 + 后缀 (2)(3)（YunX 口径）。"""
    name = sanitize_filename(filename)
    os.makedirs(folder, exist_ok=True)
    lower = name.lower()
    siblings: dict[str, str] = {}
    try:
        for e in os.scandir(folder):
            if e.is_file():
                siblings.setdefault(e.name.lower(), e.path)
    except OSError:
        pass
    same = siblings.get(lower)
    if same and os.path.getsize(same) == size:
        return same
    if same:
        stem, ext = os.path.splitext(name)
        n = 2
        while True:
            cand = f"{stem} ({n}){ext}"
            if cand.lower() not in siblings:
                name = cand
                break
            n += 1
    return os.path.join(folder, name)


async def _iter_stalled(aiter, deadline_cb):
    """按块产出字节流；两次读取间超过 STALL_TIMEOUT 判定假死。"""
    agen = aiter.__aiter__()
    while True:
        try:
            item = await asyncio.wait_for(agen.__anext__(), timeout=STALL_TIMEOUT)
            deadline_cb()
            yield item
        except StopAsyncIteration:
            return
        except asyncio.TimeoutError:
            raise StallError(f"链路假死：{STALL_TIMEOUT:.0f}s 无数据")


class FileDownloader:
    """单个文件：probe → 定名/预分配 → 并发块池 → 改名。一个实例只跑一个文件。

    final 由 folder + (filename_hint 或服务端文件名) 经 resolve_target 得出，
    因此 run() 内先 probe 拿到 total 与服务器名再定 final，然后才加载断点。
    """

    def __init__(self, client: httpx.AsyncClient, url: str, folder: str,
                 filename_hint: str = "", headers: dict | None = None,
                 block: int = 8 * 1024 * 1024, connections: int = 8,
                 on_progress=None, stop_event: asyncio.Event | None = None):
        self.client = client
        self.url = url
        self.folder = folder
        self.filename_hint = filename_hint
        self.headers = {k: v for k, v in (headers or {}).items() if v}
        self.block = block
        self.connections = max(1, min(connections, 64))
        self.on_progress = on_progress  # callable(done:int, total:int)
        self.stop_event = stop_event  # set() 表示暂停/取消；由 worker 在块边界检查

        self.final = ""
        self.total = 0
        self.server_filename = ""
        self.done: set[int] = set()
        self.partial: dict[int, int] = {}
        self.inflight: dict[int, int] = {}
        self._write_lock = asyncio.Lock()
        self._fh = None
        self._last_byte = 0.0
        self.dead = False  # 上游已死的共享标志（跨 worker）

    # ---------- probe ----------
    async def probe(self) -> int:
        """返回文件总大小；探明 Range 支持。"""
        try:
            r = await self.client.head(self.url, headers=self.headers)
            if r.status_code in (200, 206):
                size = int(r.headers.get("content-length") or 0)
                accept = (r.headers.get("accept-ranges") or "").lower()
                if size > 0 and accept in ("bytes", ""):
                    cd = filename_from_disposition(r.headers.get("content-disposition"))
                    if cd:
                        self.server_filename = cd
                    return size
        except httpx.HTTPError:
            pass
        # GET 1 字节兜底探长
        h = {**self.headers, "Range": "bytes=0-0"}
        r = await self.client.get(self.url, headers=h)
        if r.status_code == 206:
            total = parse_content_range_total(r.headers.get("content-range"))
            if total:
                cd = filename_from_disposition(r.headers.get("content-disposition"))
                if cd:
                    self.server_filename = cd
                return total
        if r.status_code == 416:
            raise FatalDownloadError("服务器拒绝 Range（416），无法断点续传")
        if r.status_code in (301, 302, 303, 307, 308):
            raise FatalDownloadError(f"直链被重定向（HTTP {r.status_code}），Cookie 可能已失效")
        if r.status_code == 403:
            raise FatalDownloadError("直链 403，凭证或提取码已失效")
        raise FatalDownloadError(f"无法探测文件长度（HTTP {r.status_code}）")

    # ---------- meta / resume ----------
    def _load_sidecar(self):
        meta = journal.read_meta(self.final)
        part = journal.part_path(self.final)
        if (meta and meta.get("size") == self.total and meta.get("block") == self.block
                and os.path.isfile(part) and os.path.getsize(part) == self.total):
            self.done = set(meta.get("done") or [])
            self.partial = {int(k): v for k, v in (meta.get("partial") or {}).items()}
            logger.debug(f"续传 {os.path.basename(self.final)}: {len(self.done)} 块已完成")
            return
        journal.delete_meta(self.final)  # 陈旧 sidecar（尺寸/块布局变了）一律作废

    def _save_meta(self):
        journal.write_meta(self.final, {
            "size": self.total, "block": self.block,
            "done": sorted(self.done),
            "partial": {str(k): v for k, v in self.partial.items() if v > 0},
        })

    def _report(self):
        if self.on_progress:
            d = journal.done_bytes(self.total, self.block, self.done, self.partial)
            try:
                self.on_progress(d, self.total)
            except Exception:
                pass

    # ---------- block ----------
    def _check_stop(self):
        if not self.stop_event or not self.stop_event.is_set():
            return
        raise PauseRequested()

    async def _fetch_block(self, idx: int):
        block_len = journal.block_len(self.total, self.block, idx)
        block_start = idx * self.block
        block_end = block_start + block_len - 1
        last_err: Exception | None = None
        for attempt in range(1, BLOCK_RETRIES + 1):
            self._check_stop()
            if idx in self.done:
                return
            already = min(self.partial.get(idx, 0), block_len)
            start = block_start + already
            if start > block_end:
                self.done.add(idx)
                self.partial.pop(idx, None)
                self._save_meta()
                return
            self._last_byte = time.monotonic()
            self.inflight[idx] = already
            try:
                h = {**self.headers, "Range": f"bytes={start}-{block_end}"}
                async with self.client.stream("GET", self.url, headers=h) as resp:
                    if resp.status_code == 200 and self.block != self.total:
                        raise FatalDownloadError("服务器忽略 Range 头（返回 200），无法并行分片")
                    if resp.status_code not in (206, 200):
                        body = (await resp.aread())[:200]
                        raise DownloadError(
                            f"HTTP {resp.status_code}: {body.decode('utf-8', 'replace').strip()[:120]}"
                            .rstrip())
                    written = already
                    async for chunk in _iter_stalled(resp.aiter_bytes(256 * 1024),
                                                     lambda: setattr(self, "_last_byte", time.monotonic())):
                        self._check_stop()
                        if not chunk:
                            continue
                        async with self._write_lock:
                            await asyncio.to_thread(self._pwrite, block_start + written, chunk)
                        written += len(chunk)
                        self.partial[idx] = written
                        self.inflight[idx] = written
                        self._report()
                if written >= block_len:
                    self.done.add(idx)
                    self.partial.pop(idx, None)
                    self.inflight.pop(idx, None)
                    self._save_meta()
                    self._report()
                    return
                last_err = DownloadError("连接提前断开")
                self.partial[idx] = written
                self._save_meta()
            except (PauseRequested, CancelRequested, FatalDownloadError):
                self.inflight.pop(idx, None)
                raise
            except (httpx.HTTPError, StallError, DownloadError) as e:
                self.inflight.pop(idx, None)
                last_err = e
                if isinstance(e, StallError):
                    # stall 多半是链路死：确认上游是否存活
                    pass
                if self.dead:
                    raise ServeDeadError(str(e)) from e
                if attempt < BLOCK_RETRIES:
                    await asyncio.sleep(RETRY_BASE_MS * attempt / 1000 + random.random() * 0.6)
        self.inflight.pop(idx, None)
        raise last_err or DownloadError("块下载失败")

    def _pwrite(self, offset: int, data: bytes):
        self._fh.seek(offset)
        self._fh.write(data)

    # ---------- run ----------
    def _resolve_final(self):
        name = self.filename_hint or self.server_filename or self.url.rsplit("/", 1)[-1] or "download.bin"
        self.final = resolve_target(self.folder, name, self.total)

    def _prep_part(self):
        """预分配 .part 为完整大小（稀疏文件），任意 offset 写入合法。"""
        part = journal.part_path(self.final)
        if not (os.path.isfile(part) and os.path.getsize(part) == self.total):
            with open(part, "wb") as f:
                f.truncate(self.total)

    async def run(self) -> str:
        """下载并返回最终路径。断点续传透明；暂停/取消抛 PauseRequested/CancelRequested。"""
        if not self.total:
            self.total = await self.probe()
        if self.total <= 0:
            raise FatalDownloadError("文件大小为 0，跳过")
        if not self.final:
            self._resolve_final()
        # 同尺寸同名文件已存在（resolve_target 复用）且无半成品 → 视为已完成
        part = journal.part_path(self.final)
        if (not os.path.isfile(part)
                and os.path.isfile(self.final) and os.path.getsize(self.final) == self.total):
            return self.final
        self._load_sidecar()
        count = (self.total + self.block - 1) // self.block
        try:
            self._prep_part()
            self._fh = open(part, "r+b")
        except OSError as e:
            raise FatalDownloadError(f"无法写入下载目录: {e}") from e
        self._save_meta()
        try:
            next_idx = iter(range(count))

            async def _pool_worker():
                while True:
                    try:
                        idx = next(next_idx)
                    except StopIteration:
                        return
                    if idx in self.done:
                        continue
                    await self._fetch_block(idx)

            workers = [asyncio.ensure_future(_pool_worker()) for _ in range(self.connections)]
            try:
                await asyncio.gather(*workers)
            finally:
                for w in workers:
                    if not w.done():
                        w.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
            missing = journal.missing_blocks(self.total, self.block, self.done)
            if missing:
                raise DownloadError(
                    f"已下载 {100 * len(self.done) // max(1, count)}% 后中断（进度已保存，可断点续传）")
        except (PauseRequested, CancelRequested):
            self._save_meta()
            raise
        finally:
            if self._fh:
                try:
                    self._fh.flush()
                    self._fh.close()
                except OSError:
                    pass
                self._fh = None
        # 完成：改名落盘 + 清理 sidecar
        try:
            os.replace(part, self.final)
        except OSError:
            try:
                os.unlink(self.final)
                os.replace(part, self.final)
            except OSError as e:
                raise DownloadError(f"重命名最终文件失败: {e}") from e
        journal.delete_meta(self.final)
        return self.final


async def probe_alive(client: httpx.AsyncClient, url: str, timeout: float = 3.0) -> bool:
    """上游存活探测（tdl serve GET /）。"""
    try:
        r = await client.get(url, timeout=timeout)
        return r.status_code < 500
    except httpx.HTTPError:
        return False
