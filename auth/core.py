"""登录管控：配置文件驱动的访问认证。

配置文件 ``data/auth.json``::

    {
      "username": "admin",
      "password": "your-password"
    }

规则（严格按需求）：
- 文件不存在，或 ``username`` / ``password`` 任一为空 → 认证关闭（保持原样，无需登录）
- 开启后：除登录接口与静态资源外，所有页面与接口都需要有效会话

会话实现：
- HttpOnly Cookie ``fongmi_session``，HMAC-SHA256 签名（密钥持久化于 data/.secret/auth.key）
- 默认 12 小时有效；登录失败按 IP 限速
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from spider.proxy_config import _CONFIG_PATH

DATA_DIR = os.path.dirname(_CONFIG_PATH)
AUTH_FILE = os.path.join(DATA_DIR, "auth.json")
_SECRET_DIR = os.path.join(DATA_DIR, ".secret")
_SECRET_FILE = os.path.join(_SECRET_DIR, "auth.key")

COOKIE_NAME = "fongmi_session"
SESSION_TTL = 12 * 3600

# 无需认证即可访问的路径
PUBLIC_PREFIXES = ("/api/auth/", "/assets/")
PUBLIC_EXACT = (
    "/login",
    "/api/health",
    "/favicon.ico",
    "/favicon.svg",
    "/robots.txt",
    "/manifest.webmanifest",
)

# 登录失败限速
_MAX_FAILS = 5
_FAIL_WINDOW = 15 * 60
_LOCKOUT = 15 * 60
_fails: dict[str, list] = {}  # ip -> [count, first_ts, locked_until]


# ---------- 配置读取 ----------

_cfg_cache: dict = {"mtime": None, "data": (False, "", "")}


def load_config() -> tuple[bool, str, str]:
    """返回 (enabled, username, password)。按 mtime 缓存，改文件即时生效。"""
    try:
        st = os.stat(AUTH_FILE)
    except OSError:
        _cfg_cache["mtime"] = None
        _cfg_cache["data"] = (False, "", "")
        return _cfg_cache["data"]
    if _cfg_cache["mtime"] == st.st_mtime:
        return _cfg_cache["data"]
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raw = {}
    except (OSError, json.JSONDecodeError):
        raw = {}
    username = str(raw.get("username") or "").strip()
    password = str(raw.get("password") or "")
    enabled = bool(username and password)
    _cfg_cache["mtime"] = st.st_mtime
    _cfg_cache["data"] = (enabled, username, password)
    return _cfg_cache["data"]


def is_enabled() -> bool:
    return load_config()[0]


def save_config(username: str, password: str) -> None:
    """写入配置文件（用于设置页管理）；空账号密码表示关闭认证。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    data = {"username": (username or "").strip(), "password": password or ""}
    tmp = AUTH_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, AUTH_FILE)
    _cfg_cache["mtime"] = None  # 使缓存失效


# ---------- 会话令牌 ----------

def _secret() -> bytes:
    os.makedirs(_SECRET_DIR, exist_ok=True)
    if os.path.isfile(_SECRET_FILE):
        with open(_SECRET_FILE, "rb") as f:
            key = f.read()
        if len(key) >= 32:
            return key
    key = secrets.token_bytes(32)
    fd = os.open(_SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    return key


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_token(username: str) -> str:
    now = int(time.time())
    payload = {"u": username, "iat": now, "exp": now + SESSION_TTL}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_token(token: str | None) -> dict | None:
    """校验令牌；有效返回 payload，否则 None。"""
    if not token or "." not in token:
        return None
    body, _, sig = token.rpartition(".")
    expect = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        payload = json.loads(_b64d(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp", 0)) < time.time():
        return None
    return payload


# ---------- 凭据校验 ----------

def verify_credentials(username: str, password: str) -> bool:
    enabled, cfg_user, cfg_pass = load_config()
    if not enabled:
        return False
    u_ok = hmac.compare_digest(username or "", cfg_user)
    p_ok = hmac.compare_digest(password or "", cfg_pass)
    return u_ok and p_ok


# ---------- 登录限速 ----------

def check_rate_limit(ip: str) -> int:
    """返回剩余锁定秒数（0 表示可尝试）。"""
    entry = _fails.get(ip)
    if not entry:
        return 0
    count, first_ts, locked_until = entry
    if locked_until and locked_until > time.time():
        return int(locked_until - time.time())
    if time.time() - first_ts > _FAIL_WINDOW:
        _fails.pop(ip, None)
    return 0


def record_failure(ip: str) -> None:
    now = time.time()
    entry = _fails.get(ip)
    if not entry or now - entry[1] > _FAIL_WINDOW:
        _fails[ip] = [1, now, 0]
        return
    entry[0] += 1
    if entry[0] >= _MAX_FAILS:
        entry[2] = now + _LOCKOUT
        entry[0] = 0
        entry[1] = now


def clear_failures(ip: str) -> None:
    _fails.pop(ip, None)


# ---------- 路径判定 ----------

def is_public_path(path: str) -> bool:
    if path in PUBLIC_EXACT:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


def client_ip(request) -> str:
    for header in ("cf-connecting-ip", "x-forwarded-for", "x-real-ip"):
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def session_status(request) -> dict:
    enabled, username, _ = load_config()
    token = request.cookies.get(COOKIE_NAME)
    payload = verify_token(token) if enabled else None
    return {
        "required": enabled,
        "authenticated": bool(payload) or not enabled,
        "username": payload.get("u") if payload else "",
        "configured_username": username if enabled else "",
    }
