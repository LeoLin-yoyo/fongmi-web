"""Proxy configuration - loads from data/config.json"""
import json
import os
import socket
import time
from urllib.parse import urlsplit

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "config.json")

_ALLOWED_SCHEMES = ("http", "https", "socks5", "socks5h", "socks4")

# 本机常见代理端口（clash / clash verge / v2rayN / privoxy 等）
_LOCAL_PROXY_PORTS = (7890, 7897, 10809, 1080, 8118, 8888)
_DETECT_TTL = 300.0
_detected: "str | None" = None
_detected_ts: float = 0.0


def _normalize_proxy(proxy: str) -> str:
    """规范化代理地址：补全 scheme 并校验协议白名单，非法值返回空串（回退直连）"""
    proxy = (proxy or "").strip()
    if not proxy:
        return ""
    if "://" not in proxy:
        proxy = "http://" + proxy
    scheme = urlsplit(proxy).scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        return ""
    return proxy


def get_system_proxy() -> str:
    """读 Windows 系统代理（IE/WinINET 设置）；非 Windows 或未开启返回空"""
    if os.name != "nt":
        return ""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        )
        try:
            enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
            if not enable:
                return ""
            server, _ = winreg.QueryValueEx(key, "ProxyServer")
        finally:
            winreg.CloseKey(key)
        if not server:
            return ""
        if "=" in server:
            # 形如 "http=127.0.0.1:7890;https=127.0.0.1:7890"，取 https/http
            parts = dict(p.split("=", 1) for p in server.split(";") if "=" in p)
            server = parts.get("https") or parts.get("http") or ""
        return _normalize_proxy(server)
    except (OSError, ValueError):
        return ""


def get_proxy() -> str:
    """代理取值优先级：设置页配置 → 环境变量 → Windows 系统代理 → 直连"""
    try:
        with open(_CONFIG_PATH, "r") as f:
            cfg = json.load(f)
        proxy = _normalize_proxy(cfg.get("proxy", ""))
        if proxy:
            return proxy
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    env = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if env:
        return _normalize_proxy(env)
    return get_system_proxy()


def detect_local_proxy() -> str:
    """探测本机常见代理端口（仅 127.0.0.1），结果按 TTL 缓存，未探到返回空"""
    global _detected, _detected_ts
    now = time.time()
    if _detected is not None and now - _detected_ts < _DETECT_TTL:
        return _detected
    found = ""
    for port in _LOCAL_PROXY_PORTS:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                found = f"http://127.0.0.1:{port}"
                break
        except OSError:
            continue
    _detected = found
    _detected_ts = now
    return found


def get_proxy_with_detect() -> str:
    """get_proxy() 为空时，再探测本机在跑的代理端口（封面图片拉取使用）"""
    proxy = get_proxy()
    if proxy:
        return proxy
    return detect_local_proxy()


def set_proxy(proxy: str):
    """Save proxy URL to config file"""
    set_config_value("proxy", proxy)


def get_config_value(key: str, default: str = "") -> str:
    """读 data/config.json 顶层字符串配置（外部播放器路径等应用级设置）"""
    try:
        with open(_CONFIG_PATH, "r") as f:
            cfg = json.load(f)
        return str(cfg.get(key, default) or "")
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def set_config_value(key: str, value: str) -> None:
    """写 data/config.json 顶层键（读-改-写，不覆盖其他键）；文件落盘，重启不丢"""
    try:
        with open(_CONFIG_PATH, "r") as f:
            cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cfg = {}
    cfg[key] = value
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    from pathlib import Path
    Path(_CONFIG_PATH).write_text(json.dumps(cfg, ensure_ascii=False, indent=2))


def get_proxy_url() -> str:
    """Get proxy URL string"""
    return get_proxy()


def get_proxy_dict():
    """Get proxy dict for backwards compat"""
    proxy = get_proxy()
    if proxy:
        return {"https://": proxy, "http://": proxy}
    return None
