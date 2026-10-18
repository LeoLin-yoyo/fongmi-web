"""TG 在线播放流式代理（移植 tdl-web lib/stream.js 的核心思路）。

serve 单连接 ~0.1MB/s 撑不起实时播放，因此在浏览器与 serve 之间加一层：
- 1MiB 分块 + 内存 LRU 缓存，浏览器每个 Range 请求从缓存块应答
- 未命中时切多子分片并行取回，边到边写响应（起播只等子分片）
- 后台预取池把播放头前方 N MB 填好
"""
import asyncio
import time
from collections import OrderedDict

from loguru import logger

from .config import get_config
from .serve import ServeSession

BLOCK = 1024 * 1024          # 1MiB 块
SUBFETCH = 4                 # 未命中时并行子分片数
STALL_TIMEOUT = 30.0
FETCH_RETRIES = 3


def parse_range(header: str | None, total: int) -> tuple[int, int] | None:
    """解析 Range 头（bytes=a-b / bytes=a- / bytes=-n），越界返回 None。"""
    if not header or total <= 0:
        return None
    header = header.strip()
    if not header.startswith("bytes="):
        return None
    spec = header[6:].split(",")[0].strip()
    if "-" not in spec:
        return None
    a, _, b = spec.partition("-")
    if a == "" and b == "":
        return None
    if a == "":
        n = int(b)
        if n <= 0:
            return None
        return max(0, total - n), total - 1
    start = int(a)
    if start >= total:
        return None
    end = int(b) if b else total - 1
    end = min(end, total - 1)
    if end < start:
        return None
    return start, end


class FileStreamer:
    """单文件的块缓存 + 预取。"""

    def __init__(self, sess: ServeSession, href: str, total: int):
        self.sess = sess
        self.href = href
        self.total = total
        self.cfg = get_config()
        self.mem: OrderedDict[int, bytes] = OrderedDict()
        self.inflight: dict[int, asyncio.Future] = {}
        self._mem_bytes = 0
        self._cache_cap = self.cfg.stream_cache_mb * 1024 * 1024
        self._window = max(1, self.cfg.stream_window_mb * 1024 * 1024 // BLOCK)
        self._pool = max(1, min(self.cfg.stream_connections, 64))
        self.cursor = 0
        self.last_hit = time.time()
        self._prefetch_task: asyncio.Task | None = None

    def _block_len(self, idx: int) -> int:
        return min(BLOCK, self.total - idx * BLOCK)

    def _put(self, idx: int, data: bytes):
        if idx in self.mem:
            self._mem_bytes -= len(self.mem[idx])
        self.mem[idx] = data
        self._mem_bytes += len(data)
        self.mem.move_to_end(idx)
        while self._mem_bytes > self._cache_cap and self.mem:
            self.mem.popitem(last=False)

    async def _fetch_range(self, start: int, end: int) -> bytes:
        last_err = None
        for attempt in range(FETCH_RETRIES):
            try:
                resp = await self.sess.local_request(
                    self.href, headers={"Range": f"bytes={start}-{end}"}, timeout=STALL_TIMEOUT)
                if resp.status_code in (200, 206):
                    data = resp.content
                    want = end - start + 1
                    if len(data) >= want:
                        return data[:want]
                    if resp.status_code == 200 and self.total == len(data):
                        return data[start:start + want]
                    last_err = ValueError(f"提前断开 {len(data)}/{want}")
                else:
                    last_err = ValueError(f"HTTP {resp.status_code}")
            except Exception as e:
                last_err = e
            await asyncio.sleep(0.4 * (attempt + 1))
        raise last_err or ValueError("分块获取失败")

    async def block(self, idx: int) -> bytes:
        """取整块（缓存优先，未命中并行子分片）。"""
        if idx in self.mem:
            self.mem.move_to_end(idx)
            return self.mem[idx]
        if idx in self.inflight:
            return await self.inflight[idx]
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self.inflight[idx] = fut
        try:
            start = idx * BLOCK
            blen = self._block_len(idx)
            if self._pool <= 1 or blen <= BLOCK // SUBFETCH:
                data = await self._fetch_range(start, start + blen - 1)
            else:
                # 并行子分片：先到先写，起播只等第一片
                parts = SUBFETCH
                step = blen // parts
                tasks = []
                for i in range(parts):
                    s = start + i * step
                    e = start + blen - 1 if i == parts - 1 else start + (i + 1) * step - 1
                    tasks.append(self._fetch_range(s, e))
                chunks = await asyncio.gather(*tasks)
                data = b"".join(chunks)
            self._put(idx, data)
            if not fut.done():
                fut.set_result(data)
            return data
        except Exception as e:
            if not fut.done():
                fut.set_exception(e)
            raise
        finally:
            self.inflight.pop(idx, None)

    def note_cursor(self, block_idx: int):
        self.cursor = block_idx
        self.last_hit = time.time()
        self._schedule_prefetch()

    def is_playing(self, timeout: float = 60.0) -> bool:
        """最近 timeout 秒内是否仍有拉流动作（用于判断会话是否正在被播放）。"""
        return time.time() - self.last_hit <= timeout

    def _schedule_prefetch(self):
        if self._prefetch_task and not self._prefetch_task.done():
            return
        self._prefetch_task = asyncio.create_task(self._prefetch())

    async def _prefetch(self):
        count = (self.total + BLOCK - 1) // BLOCK
        start = self.cursor + 2
        end = min(self.cursor + self._window, count)
        sem = asyncio.Semaphore(self._pool)

        async def one(i: int):
            if i in self.mem or i in self.inflight:
                return
            async with sem:
                try:
                    await self.block(i)
                except Exception:
                    pass

        try:
            await asyncio.gather(*[one(i) for i in range(start, end)])
        except Exception:
            pass

    async def iter_range(self, start: int, end: int):
        """按块产出 [start, end] 的字节（自动裁剪到请求范围）。"""
        pos = start
        while pos <= end:
            idx = pos // BLOCK
            off = pos - idx * BLOCK
            self.note_cursor(idx)
            data = await self.block(idx)
            piece = data[off:]
            need = end - pos + 1
            if len(piece) > need:
                piece = piece[:need]
            yield piece
            pos += len(piece)
            if not piece:
                break

    def stats(self) -> dict:
        return {"cursor": self.cursor, "cached_blocks": len(self.mem),
                "cache_mb": round(self._mem_bytes / 1024 / 1024, 1),
                "window": self._window, "pool": self._pool}


_streamers: dict[str, FileStreamer] = {}


def active_stream_keys(timeout: float = 60.0) -> set[str]:
    """正在被播放（近期有拉流）的 streamer key 集合。"""
    return {k for k, st in _streamers.items() if st.is_playing(timeout)}


def get_streamer(sess: ServeSession, href: str, total: int) -> FileStreamer:
    key = f"{sess.sid}:{href}"
    st = _streamers.get(key)
    if st is None or st.total != total:
        st = FileStreamer(sess, href, total)
        _streamers[key] = st
    return st


def drop_streamers(sid: str):
    for k in [k for k in _streamers if k.startswith(f"{sid}:")]:
        _streamers.pop(k, None)
