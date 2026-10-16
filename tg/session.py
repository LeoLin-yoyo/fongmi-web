"""tdl 会话与聊天列表（移植 tdl-web lib/chats.js 口径）。"""
import asyncio
import json
import time

from .config import get_config
from .runner import runner

_chat_cache: dict = {"data": None, "ts": 0.0}
CHAT_TTL = 600.0


async def list_chats(refresh: bool = False) -> list:
    """`tdl chat ls -o json`，TTL 10 分钟缓存。"""
    now = time.time()
    if not refresh and _chat_cache["data"] is not None and now - _chat_cache["ts"] < CHAT_TTL:
        return _chat_cache["data"]
    cfg = get_config()
    args = runner_global(cfg) + ["chat", "ls", "-o", "json"]

    async def _run():
        return await runner.collect(args, timeout=120, configured_path=cfg.tdl_path)

    out = await runner.enqueue("chat ls", _run)
    text = out.strip()
    # 截取第一个 [ 到最后一个 ]
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < 0:
        if "database is used by another process" in text:
            raise RuntimeError("tdl 数据库被其他进程占用，请稍后重试")
        raise RuntimeError("未获取到会话列表（可能尚未登录）")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        raise RuntimeError("会话列表解析失败")
    _chat_cache["data"] = data
    _chat_cache["ts"] = now
    return data


def runner_global(cfg=None) -> list:
    cfg = cfg or get_config()
    args: list[str] = []
    if cfg.proxy:
        args += ["--proxy", cfg.proxy]
    if cfg.ns:
        args += ["--ns", cfg.ns]
    return args


def invalidate():
    _chat_cache["data"] = None
    _chat_cache["ts"] = 0.0
