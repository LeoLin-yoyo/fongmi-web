"""tdl 交互式登录（移植 tdl-web lib/login.js 的状态机口径）。

tdl 的 survey 提示在管道下会失败，必须用 PTY；提示文本不带换行，
因此提示检测在滚动 chunk 上做，二维码块按行累积。
登录成功以「会话是否可用」判定（tdl 成功后本就 exit 0，与失败混淆）。
"""
import asyncio
import os
import re
import time
from loguru import logger

from .config import get_config
from .runner import runner, strip_ansi

QR_BLOCK_RE = re.compile(r"^[\u2580\u2584\u2588\u2592\u0020]+$")
RE_SUCCESS = re.compile(r"Login successfully! ID: (\d+), Username:\s*(\S*)")
RE_IMPORT_OK = re.compile(r"Import (\d+) successfully to '([^']+)' namespace")
RE_SELECT_USER = re.compile(r"Choose a user id")
RE_CONFIRM_LOGOUT = re.compile(r"logout existing desktop session")
RE_ERR_DB = re.compile(r"database is used by another process")


class LoginSession:
    def __init__(self):
        self.state = "idle"   # idle/starting/qr/code/password/select/checking/success/failed/canceled
        self.error = ""
        self.qr_text = ""
        self.user = None
        self.kind = ""
        self.ns = ""
        self.phone = ""
        self._proc = None
        self._master_fd = None
        self._qr_lines: list[str] = []
        self._qr_last = 0.0
        self._sent_phone = False
        self._user_ids: list[str] = []
        self._last_output = 0.0
        self._lines: list[str] = []
        self._chunk_tail = ""
        self._task: asyncio.Task | None = None

    def public(self) -> dict:
        return {"state": self.state, "error": self.error, "user": self.user,
                "kind": self.kind, "ns": self.ns, "qr": bool(self.qr_text)}

    def _log(self, s):
        self._lines.append(s)
        if len(self._lines) > 200:
            self._lines = self._lines[-200:]
        self._last_output = time.time()

    def _flush_qr(self):
        if len(self._qr_lines) >= 4:
            self.qr_text = "\n".join(self._qr_lines)
            self.state = "qr"

    def on_chunk(self, text: str):
        """PTY 输出是无换行滚动流：提示检测在 chunk 上做。"""
        self._log(text)
        buf = self._chunk_tail + text
        # 二维码块行
        for line in buf.split("\n"):
            if QR_BLOCK_RE.match(line) and len(line.strip()) >= 8:
                self._qr_lines.append(line.rstrip("\r"))
                self._qr_last = time.time()
            elif self._qr_lines and time.time() - self._qr_last > 0.6:
                self._flush_qr()
                self._qr_lines = []
        self._chunk_tail = buf[-200:]
        # 提示检测
        tail = text
        if "Enter 2FA Password" in tail:
            self.state = "password"
        if "Enter your phone number" in tail and self.kind == "code" and not self._sent_phone:
            self._write(self.phone + "\r")
            self._sent_phone = True
        if "Enter Code" in tail and self.kind == "code":
            self.state = "code"
        if RE_SELECT_USER.search(tail):
            self.state = "select"
            self._user_ids = []
            asyncio.create_task(self._auto_pick())
        if RE_CONFIRM_LOGOUT.search(tail):
            # 自动答「否」，绝不登出用户的桌面端
            self._write("\r")
        # 行级
        for line in strip_ansi(text).replace("\r", "\n").split("\n"):
            line = line.strip()
            if not line:
                continue
            m = RE_SUCCESS.search(line)
            if m:
                self.user = {"id": m.group(1), "username": m.group(2)}
                self.state = "success"
            elif RE_IMPORT_OK.search(line):
                self.state = "success"
            elif RE_ERR_DB.search(line):
                self.error = "tdl 数据库被其他进程占用，请稍后重试"
            elif self.state == "select":
                m = re.match(r"^[>\s]*0*(\d{4,})\s*$", line)
                if m:
                    self._user_ids.append(m.group(1))

    async def _auto_pick(self):
        await asyncio.sleep(1.8)
        if self.state == "select" and len(self._user_ids) == 1:
            self._write(self._user_ids[0] + "\r")
            self.state = "checking"

    def _write(self, s: str):
        data = s.encode()
        # PTY 模式：stdin 是 slave fd，用 master fd 写入；管道模式：stdin pipe
        if self._master_fd is not None:
            try:
                os.write(self._master_fd, data)
            except OSError:
                pass
            return
        if self._proc and self._proc.stdin and not self._proc.stdin.is_closing():
            try:
                self._proc.stdin.write(data)
            except Exception:
                pass


class LoginManager:
    def __init__(self):
        self.session = LoginSession()
        self._login_state = "unknown"

    async def detect_async(self) -> str:
        """探测会话是否可用：`tdl chat ls -o json` 能列出即已登录。"""
        from .session import list_chats
        try:
            chats = await list_chats()
            self._login_state = "logged_in"
            return "logged_in"
        except Exception as e:
            msg = str(e)
            if "数据库" in msg or "database" in msg.lower():
                self._login_state = "busy"
            else:
                self._login_state = "logged_out"
            return self._login_state

    def status(self) -> dict:
        return {"loginState": self._login_state, "session": self.session.public()}

    async def start(self, kind: str, phone: str = "", ns: str = "") -> LoginSession:
        cfg = get_config()
        sess = LoginSession()
        sess.kind = kind
        sess.phone = phone
        sess.ns = ns or cfg.ns
        sess.state = "starting"
        self.session = sess
        sess._task = asyncio.create_task(self._run(sess))
        return sess

    async def _run(self, sess: LoginSession):
        cfg = get_config()
        import os
        from .runner import sanitize_args
        args = []
        if cfg.proxy:
            args += ["--proxy", cfg.proxy]
        if sess.ns:
            args += ["--ns", sess.ns]
        args += ["login", "-T", "code" if sess.kind == "code" else "qr"]
        try:
            exe = runner.require_path(cfg.tdl_path)
        except Exception as e:
            sess.state = "failed"
            sess.error = str(e)
            return

        env = dict(os.environ)
        env["COLUMNS"] = "400"
        import pty
        master, slave = pty.openpty() if os.name != "nt" else (None, None)
        sess._master_fd = master
        try:
            if os.name == "nt":
                proc = await asyncio.create_subprocess_exec(
                    exe, *sanitize_args(args), stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                    env=env, cwd=os.path.dirname(exe) or None)
            else:
                proc = await asyncio.create_subprocess_exec(
                    exe, *sanitize_args(args), stdin=slave, stdout=slave, stderr=slave,
                    env=env, cwd=os.path.dirname(exe) or None)
                os.close(slave)

            sess._proc = proc

            if os.name == "nt":
                assert proc.stdout
                while True:
                    chunk = await proc.stdout.read(4096)
                    if not chunk:
                        break
                    sess.on_chunk(chunk.decode("utf-8", "replace"))
            else:
                loop = asyncio.get_event_loop()
                while True:
                    try:
                        chunk = await loop.run_in_executor(None, os.read, master, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    sess.on_chunk(chunk.decode("utf-8", "replace"))
            # 最后 flush 二维码
            sess._flush_qr()

            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

            # 退出判定：tdl 成功也 exit 0，以会话可用性为准
            if sess.state != "success":
                await asyncio.sleep(0.8)
                if await self.detect_async() == "logged_in":
                    sess.state = "success"
                elif sess.state not in ("canceled",):
                    sess.state = "failed"
                    sess.error = sess.error or "登录未完成或会话校验未通过"
            if sess.state == "success":
                self._login_state = "logged_in"
        except Exception as e:
            sess.state = "failed"
            sess.error = str(e)[:200]
            logger.error(f"TG 登录失败: {e}")
        finally:
            try:
                if os.name != "nt" and master is not None:
                    os.close(master)
            except OSError:
                pass

    def submit_input(self, value: str) -> bool:
        sess = self.session
        if sess.state == "select":
            digits = re.sub(r"\D", "", value or "")
            if not digits:
                return False
            sess._write(digits + "\r")
            sess.state = "checking"
            return True
        if sess.state in ("password", "code"):
            sess._write((value or "") + "\r")
            sess.state = "checking"
            return True
        return False

    async def cancel(self) -> bool:
        sess = self.session
        sess.state = "canceled"
        if sess._proc and sess._proc.returncode is None:
            try:
                sess._proc.kill()
            except ProcessLookupError:
                pass
        return True


login_manager = LoginManager()
