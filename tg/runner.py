"""tdl 执行器（移植 tdl-web lib/tdl.js 的算法，Python asyncio 重写）。

核心约定：
- 全局串行队列：tdl 的 bolt 数据库同时只允许一个写入进程
- 参数以净化后的数组传递，永不经过 shell
- 进度行解析：ANSI 剥离 + go-pretty 正则 + `-> ` 拆出落盘路径
- 终端宽度 400 列，否则进度行里的落盘绝对路径被截断
"""
import asyncio
import os
import re
import shutil
import time
from loguru import logger

# 终端宽度：go-pretty 的 message 列会把路径截断成 F:\telegr~
PTY_COLS = 400
PTY_ROWS = 40

# ---- ANSI 剥离 ----
_ANSI_RE = re.compile(r"\x1b(?:\[[0-9;?]*[A-Za-z@]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")


def strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


def sanitize_args(args: list[str]) -> list[str]:
    """去掉控制字符，防参数注入。"""
    return [re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(a)) for a in args]


# ---- go-pretty 进度行正则（tdl-web classifyLine 口径） ----
RE_DONE = re.compile(r"^(.*?)\s*\.{0,3}\s*done!\s*\[([\d.]+\s*\w+B) in ([^;]+)(?:;\s*([^\]]+))?\]\s*$")
RE_FAILED = re.compile(r"^(.*?)\s*\.{0,3}\s*failed!\s*\[([^\]]*)\]\s*$")
RE_PROG = re.compile(
    r"^(.*?)\s*\.{0,3}\s*([\d.]+)%\s*\[[#.\s]*\]\s*\[(.+?) in ([^;]+);\s*~ETA:\s*([^;]+);\s*([^\]]+)\]\s*$")
RE_PROG_NOETA = re.compile(
    r"^(.*?)\s*\.{0,3}\s*([\d.]+)%\s*\[[#.\s]*\]\s*\[(.+?) in ([^;]+);\s*([^\]]+)\]\s*$")
RE_OVERALL = re.compile(r"^\[[#.\s]+\]\s*\[")
RE_MSG_ARROW = re.compile(r"^(.*?)\s+->\s+(.+)$")

_SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}


def parse_size(s: str) -> int:
    m = re.match(r"([\d.]+)\s*(\w+)?", (s or "").strip())
    if not m:
        return 0
    val = float(m.group(1))
    unit = (m.group(2) or "B").upper()
    return int(val * _SIZE_UNITS.get(unit, 1))


def split_message(msg: str) -> tuple[str, str]:
    """tdl 每文件消息形如 `<peer>(<id>):<msgid> -> <落盘路径>` → (label, path)。"""
    m = RE_MSG_ARROW.match(msg or "")
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return (msg or "").strip(), ""


def classify_line(line: str) -> dict:
    """解析单行 tdl 输出 → {kind, ...}。"""
    s = strip_ansi(line).replace("\r", "").rstrip()
    if not s.strip():
        return {"kind": "empty"}
    if RE_OVERALL.match(s):
        return {"kind": "overall"}

    m = RE_DONE.match(s)
    if m:
        label, path = split_message(m.group(1))
        return {"kind": "itemDone", "name": label, "label": label, "path": path,
                "size": parse_size(m.group(2)), "elapsed": m.group(3), "tail": m.group(4) or ""}
    m = RE_FAILED.match(s)
    if m:
        label, path = split_message(m.group(1))
        return {"kind": "itemFailed", "name": label, "label": label, "path": path,
                "tail": m.group(2)}

    # 进度行可能带 `-> <落盘路径>` 后缀：先剥掉再匹配，路径单独保留
    body, tail_path = s, ""
    arrow = RE_MSG_ARROW.match(s)
    if arrow and "%" in s:
        body, tail_path = arrow.group(1).rstrip(), arrow.group(2).strip()

    m = RE_PROG.match(body)
    if m:
        label, path = split_message(m.group(1))
        pct = float(m.group(2))
        done = parse_size(m.group(3))            # group3 = 已完成字节
        speed = parse_size(m.group(6))           # group6 = 速度；group4=耗时 group5=ETA
        return {"kind": "itemProgress", "name": label, "label": label,
                "path": tail_path or path,
                "pct": pct, "done_bytes": done,
                "total": int(done / (pct / 100)) if pct > 0 else 0,
                "speed_bps": speed, "eta": m.group(5)}
    m = RE_PROG_NOETA.match(body)
    if m:
        label, path = split_message(m.group(1))
        pct = float(m.group(2))
        done = parse_size(m.group(3))
        speed = parse_size(m.group(5))           # 无 ETA：group4=耗时 group5=速度
        return {"kind": "itemProgress", "name": label, "label": label,
                "path": tail_path or path,
                "pct": pct, "done_bytes": done,
                "total": int(done / (pct / 100)) if pct > 0 else 0,
                "speed_bps": speed, "eta": ""}
    return {"kind": "log", "text": s}


class TdlNotFound(Exception):
    pass


class TdlError(Exception):
    pass


class TdlRunner:
    """全局单例：串行队列 + 进程管理。"""

    def __init__(self):
        self.path = ""
        self._queue_tail: asyncio.Future | None = None
        self._active: str | None = None
        self._lock = asyncio.Lock()

    # ---------- 路径发现 ----------
    def locate(self, configured: str = "") -> str:
        candidates = []
        if configured:
            candidates.append(configured)
        candidates.append(os.environ.get("TDL_GUI_TDL_PATH", ""))
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates.append(os.path.join(root, "tdl", "tdl"))
        candidates.append(os.path.join(root, "tdl", "tdl.exe"))
        for c in candidates:
            if c and os.path.isfile(c) and os.access(c, os.X_OK):
                self.path = c
                return c
        found = shutil.which("tdl")
        self.path = found or ""
        return self.path

    def require_path(self, configured: str = "") -> str:
        p = self.locate(configured)
        if not p:
            raise TdlNotFound("未找到 tdl 可执行文件，请在「设置 → Telegram」中配置路径或自动下载")
        return p

    # ---------- 串行队列 ----------
    async def enqueue(self, name: str, coro_factory):
        """把所有 tdl 调用串行化（bolt 单写者）。"""
        async with self._lock:
            prev = self._queue_tail
            loop = asyncio.get_event_loop()
            done = loop.create_future()
            self._queue_tail = done
        if prev is not None:
            try:
                await asyncio.wait_for(asyncio.shield(prev), timeout=1800)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass
        self._active = {"name": name, "startedAt": time.time()}
        try:
            return await coro_factory()
        finally:
            self._active = None
            if not done.done():
                done.set_result(True)

    def queue_info(self) -> dict | None:
        return dict(self._active) if self._active else None

    # ---------- 执行 ----------
    async def run(self, args: list[str], timeout: int = 1800,
                  on_line=None, interactive: bool = False, configured_path: str = "") -> dict:
        """跑一次 tdl。interactive=True 时用 PTY（登录），否则普通管道。

        返回 {exit_code, timed_out, stdout}。
        """
        exe = self.require_path(configured_path)
        clean = sanitize_args(args)
        env = dict(os.environ)
        env["TERM"] = "xterm-256color"
        env["COLUMNS"] = str(PTY_COLS)
        env["LINES"] = str(PTY_ROWS)

        if interactive:
            return await self._run_pty(exe, clean, env, timeout, on_line)
        return await self._run_pipe(exe, clean, env, timeout, on_line)

    async def _run_pipe(self, exe, args, env, timeout, on_line):
        proc = await asyncio.create_subprocess_exec(
            exe, *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL, env=env,
            cwd=os.path.dirname(exe) or None,
        )
        out: list[str] = []
        buf = ""

        async def pump():
            nonlocal buf
            assert proc.stdout
            while True:
                chunk = await proc.stdout.read(4096)
                if not chunk:
                    break
                text = chunk.decode("utf-8", "replace")
                out.append(text)
                buf += text
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    if on_line:
                        try:
                            on_line(line)
                        except Exception:
                            pass
            if buf and on_line:
                on_line(buf)

        timed_out = False
        try:
            await asyncio.wait_for(asyncio.gather(pump(), proc.wait()), timeout=timeout)
        except asyncio.TimeoutError:
            timed_out = True
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
        return {"exit_code": proc.returncode, "timed_out": timed_out, "stdout": "".join(out)}

    async def _run_pty(self, exe, args, env, timeout, on_line):
        """PTY 交互执行（登录用）。POSIX 用 pty，Windows 回退 pipe。"""
        if os.name == "nt":
            return await self._run_pipe(exe, args, env, timeout, on_line)
        import pty
        master, slave = pty.openpty()
        try:
            import fcntl, struct, termios
            fcntl.ioctl(slave, termios.TIOCSWINSZ,
                        struct.pack("HHHH", PTY_ROWS, PTY_COLS, 0, 0))
        except (ImportError, OSError):
            pass
        proc = await asyncio.create_subprocess_exec(
            exe, *args, stdin=slave, stdout=slave, stderr=slave, env=env,
            cwd=os.path.dirname(exe) or None,
        )
        os.close(slave)
        loop = asyncio.get_event_loop()
        out: list[str] = []
        buf = ""

        async def read_loop():
            nonlocal buf
            while True:
                try:
                    chunk = await loop.run_in_executor(None, os.read, master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                text = chunk.decode("utf-8", "replace")
                out.append(text)
                if on_line:
                    try:
                        on_line(text)
                    except Exception:
                        pass

        timed_out = False
        try:
            await asyncio.wait_for(asyncio.gather(read_loop(), proc.wait()), timeout=timeout)
        except asyncio.TimeoutError:
            timed_out = True
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
        finally:
            try:
                os.close(master)
            except OSError:
                pass
        return {"exit_code": proc.returncode, "timed_out": timed_out, "stdout": "".join(out)}

    async def collect(self, args: list[str], timeout: int = 180, configured_path: str = "") -> str:
        """收集纯文本输出（ANSId 已剥）。"""
        res = await self.run(args, timeout=timeout, configured_path=configured_path)
        return strip_ansi(res["stdout"])


runner = TdlRunner()
