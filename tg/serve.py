"""tdl serve 会话与文件清单解析。

tdl `dl --serve` 会起一个本地 HTTP 服务，根索引页是 `<a href="peer/msg">` 列表，
每个文件可按 `HEAD/GET /<peer>/<msg>` 拿元数据与字节流（支持 Range）。
本模块负责：起/停 serve 进程、解析索引、HEAD 富化、loopback 安全构造。
"""
import asyncio
import os
import re
import secrets
import time
from urllib.parse import unquote

import httpx
from loguru import logger

from . import tdlfetch
from .config import get_config
from .runner import runner

LOCAL_HOST = "127.0.0.1"
_IDX_HREF = re.compile(r"<a\s+href=\"([^\"]+)\"", re.I)
_HREF_DIGITS = re.compile(r"^(\d{1,20})/(\d{1,20})$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.%-]*$")

PLAYABLE_EXT = {"mp4", "m4v", "webm", "mov", "mkv", "mp3", "m4a", "aac", "wav", "ogg", "flac"}
MIME = {
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".mkv": "video/x-matroska", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
    ".aac": "audio/aac", ".wav": "audio/wav", ".ogg": "audio/ogg", ".flac": "audio/flac",
}


def parse_href(raw: str) -> tuple[int, int] | None:
    """tdl serve 索引 href 形如 <peerID>/<messageID>（两段皆数字）。"""
    m = _HREF_DIGITS.match((raw or "").strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def parse_index(html: str) -> list[str]:
    return _IDX_HREF.findall(html or "")


def mime_of(name: str) -> str:
    return MIME.get(os.path.splitext(name)[1].lower(), "application/octet-stream")


def is_playable(name: str) -> bool:
    return os.path.splitext(name)[1].lower().lstrip(".") in PLAYABLE_EXT


class ServeSession:
    """一个 tdl serve 进程 + 其文件清单。"""

    def __init__(self, sid: str, port: int, base: str, dir: str):
        self.sid = sid
        self.port = port
        self.base = base           # http://127.0.0.1:<port>
        self.dir = dir
        self.proc = None
        self.files: list[dict] = []
        self.state = "starting"    # starting / ready / failed / stopped
        self.error = ""
        self.last_used = time.time()

    def touch(self):
        self.last_used = time.time()

    async def local_request(self, path: str, method: str = "GET", headers: dict | None = None,
                            timeout: float = 30, stream: bool = False):
        """loopback 安全请求：host 硬编码、path 已校验。空路径（索引页）单独放行。"""
        rel = path.lstrip("/")
        if rel and not _SAFE_PATH.match(rel):
            raise ValueError(f"非法路径: {path[:60]}")
        client = httpx.AsyncClient(follow_redirects=False, verify=False,
                                   timeout=httpx.Timeout(timeout))
        try:
            req = client.build_request(method, f"{self.base}/{rel}", headers=headers or {})
            if stream:
                return client, await client.send(req, stream=True)
            resp = await client.send(req)
            return resp
        finally:
            if not stream:
                await client.aclose()


class ServeManager:
    """管理所有 serve 会话（播放 + 下载共用）。"""

    def __init__(self):
        self.sessions: dict[str, ServeSession] = {}
        self._ports: set[int] = set()

    def _next_port(self, seed: str) -> int:
        for i in range(200):
            port = 28900 + (abs(hash(seed + str(i))) % 200)
            if port not in self._ports:
                self._ports.add(port)
                return port
        raise RuntimeError("无可用端口")

    def _release_port(self, port: int):
        self._ports.discard(port)

    def build_dl_args(self, urls: list[str], out_dir: str, cfg=None) -> list[str]:
        """构造 `tdl dl` 参数（不含 --serve，由 start 追加）。"""
        cfg = cfg or get_config()
        args = ["dl"]
        for u in urls:
            args += ["-u", u]
        args += ["--dir", out_dir]
        if cfg.include:
            args += ["--include", _ext_pair(cfg.include)]
        if cfg.exclude:
            args += ["--exclude", _ext_pair(cfg.exclude)]
        args += ["--continue"]  # 默认续传，避免卡确认
        return args

    def global_args(self, cfg=None) -> list[str]:
        cfg = cfg or get_config()
        args: list[str] = []
        if cfg.proxy:
            args += ["--proxy", cfg.proxy]
        if cfg.ns:
            args += ["--ns", cfg.ns]
        return args

    async def start(self, urls: list[str], out_dir: str, sid: str = "") -> ServeSession:
        cfg = get_config()
        sid = sid or secrets.token_hex(4)
        port = self._next_port(sid)
        base = f"http://{LOCAL_HOST}:{port}"
        sess = ServeSession(sid, port, base, out_dir)
        self.sessions[sid] = sess

        args = self.global_args(cfg) + self.build_dl_args(urls, out_dir, cfg)
        args += ["--serve", "--port", str(port)]

        runner.require_path(cfg.tdl_path)

        async def _spawn():
            exe = runner.require_path(cfg.tdl_path)
            from .runner import sanitize_args
            env = dict(os.environ)
            env["COLUMNS"] = "400"
            proc = await asyncio.create_subprocess_exec(
                exe, *sanitize_args(args),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL, env=env,
                cwd=os.path.dirname(exe) or None,
            )
            sess.proc = proc
            asyncio.create_task(self._drain(sess, proc))
            return proc

        await runner.enqueue(f"serve:{sid}", _spawn)

        # 就绪等待：最多 ~25s
        ready = await self._wait_ready(sess)
        if not ready:
            await self._kill(sess)
            sess.state = "failed"
            sess.error = "tdl serve 启动超时（请检查代理是否可用）"
            return sess

        html = await self._fetch_index(sess)
        hrefs = parse_index(html)
        sess.files = await self._enrich(sess, hrefs)
        sess.state = "ready"
        logger.info(f"TG serve 就绪 sid={sid} 文件数={len(sess.files)}")
        return sess

    async def _drain(self, sess: ServeSession, proc):
        assert proc.stdout
        try:
            while True:
                chunk = await proc.stdout.read(4096)
                if not chunk:
                    break
        except Exception:
            pass

    async def _kill(self, sess: ServeSession):
        if sess.proc and sess.proc.returncode is None:
            try:
                sess.proc.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(sess.proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass
        self._release_port(sess.port)

    async def _wait_ready(self, sess: ServeSession) -> bool:
        for _ in range(25):
            try:
                resp = await sess.local_request("", timeout=3)
                if resp.status_code < 500:
                    return True
            except Exception:
                pass
            await asyncio.sleep(1.0)
        return False

    async def _fetch_index(self, sess: ServeSession) -> str:
        for _ in range(3):
            try:
                resp = await sess.local_request("", timeout=8)
                return resp.text
            except Exception:
                await asyncio.sleep(1.0)
        return ""

    async def _enrich(self, sess: ServeSession, hrefs: list[str]) -> list[dict]:
        out = []
        sem = asyncio.Semaphore(6)

        async def one(href: str):
            pair = parse_href(href)
            if not pair:
                return
            async with sem:
                try:
                    resp = await sess.local_request(f"{pair[0]}/{pair[1]}", method="HEAD", timeout=15)
                    name = _filename_from_headers(resp.headers) or f"{pair[1]}.bin"
                    size = int(resp.headers.get("content-length") or 0)
                    out.append({
                        "href": f"{pair[0]}/{pair[1]}", "peer": pair[0], "msg": pair[1],
                        "name": name, "size": size, "ext": os.path.splitext(name)[1].lstrip(".").lower(),
                        "playable": is_playable(name),
                    })
                except Exception as e:
                    logger.debug(f"HEAD {href} 失败: {e}")

        await asyncio.gather(*[one(h) for h in hrefs])
        out.sort(key=lambda x: x["name"])
        return out

    async def stop(self, sid: str) -> bool:
        sess = self.sessions.pop(sid, None)
        if not sess:
            return False
        await self._kill(sess)
        sess.state = "stopped"
        return True

    async def stop_all(self):
        for sid in list(self.sessions.keys()):
            await self.stop(sid)

    def get(self, sid: str) -> ServeSession | None:
        return self.sessions.get(sid)

    def list(self) -> list[dict]:
        return [{"sid": s.sid, "state": s.state, "count": len(s.files), "dir": s.dir}
                for s in self.sessions.values()]


def _ext_pair(csv: str) -> str:
    """tdl 的 --include/--exclude 按原始大小写精确匹配，需同时传大小写两种。"""
    exts = [e.strip().lstrip(".") for e in re.split(r"[,，]", csv or "") if e.strip()]
    out = []
    for e in exts:
        out.append(e.lower())
        if e.upper() != e.lower():
            out.append(e.upper())
    return ",".join(out)


def _filename_from_headers(headers) -> str:
    cd = headers.get("content-disposition") or ""
    m = re.search(r"filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)", cd)
    if m:
        return unquote(m.group(1).strip().strip('"'))
    m = re.search(r'filename\s*=\s*"([^"]+)"', cd)
    if m:
        raw = m.group(1)
        try:
            return raw.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return raw
    return ""


serve_manager = ServeManager()
