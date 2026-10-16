"""平台注册表：客户端工厂 + 账号 Cookie 注入 + Set-Cookie 回写。

cookie_sink 把服务端重新下发的 __puus/__pus 合并回加密库（会话保鲜，YunX AList 口径）。
"""
import asyncio

from loguru import logger
from sqlalchemy import select

from model.database import PanAccount as AccountRow
from model.database import async_session

from . import crypto
from .base import PanClient
from .platforms.baidu import BaiduClient
from .platforms.c139 import C139Client
from .platforms.guangya import GuangYaClient
from .platforms.ilanzou import ILanzouClient
from .platforms.lanzou import LanzouClient
from .platforms.pan115 import Pan115Client
from .platforms.pan123 import Pan123Client
from .platforms.quark import QuarkClient
from .platforms.uc import UCClient
from .platforms.xunlei import XunleiClient

CLIENT_CLASSES: dict[str, type[PanClient]] = {
    QuarkClient.platform: QuarkClient,
    UCClient.platform: UCClient,
    XunleiClient.platform: XunleiClient,
    BaiduClient.platform: BaiduClient,
    C139Client.platform: C139Client,
    Pan123Client.platform: Pan123Client,
    Pan115Client.platform: Pan115Client,
    GuangYaClient.platform: GuangYaClient,
    LanzouClient.platform: LanzouClient,
    ILanzouClient.platform: ILanzouClient,
}

_clients: dict[str, PanClient] = {}
_lock = asyncio.Lock()


def platform_label(key: str) -> str:
    cls = CLIENT_CLASSES.get(key)
    return cls.label if cls else key


def guest_supported(key: str) -> bool:
    cls = CLIENT_CLASSES.get(key)
    return bool(cls and cls.GUEST_SUPPORTED)


async def _load_cookie(platform: str) -> str:
    async with async_session() as session:
        row = (await session.execute(
            select(AccountRow).where(AccountRow.platform == platform)
        )).scalar_one_or_none()
    if not row or not row.cookie:
        return ""
    try:
        return crypto.decrypt(row.cookie)
    except Exception as e:
        logger.error(f"{platform} Cookie 解密失败（密钥变更？）: {e}")
        return ""


def _sink_factory(platform: str):
    """同步回调（httpx 响应线程内触发）→ 异步落库调度。"""
    def sink(_platform: str, merged_cookie: str):
        async def persist():
            async with async_session() as session:
                row = (await session.execute(
                    select(AccountRow).where(AccountRow.platform == platform)
                )).scalar_one_or_none()
                if row:
                    row.cookie = crypto.encrypt(merged_cookie)
                    await session.commit()
        try:
            asyncio.create_task(persist())
        except RuntimeError:
            pass  # 不在事件循环内（理论上不会发生）
    return sink


async def get_client(platform: str) -> PanClient | None:
    """取平台客户端（带最新账号 Cookie；未登录则空 Cookie，仅游客链路可用）。"""
    cls = CLIENT_CLASSES.get(platform)
    if not cls:
        return None
    async with _lock:
        client = _clients.get(platform)
        if client is None:
            cookie = await _load_cookie(platform)
            client = cls(cookie=cookie, cookie_sink=_sink_factory(platform))
            _clients[platform] = client
        else:
            # 账号可能在设置页更新过：每次解析前从库里同步最新 Cookie
            cookie = await _load_cookie(platform)
            if cookie and cookie != client.cookie:
                client.cookie = cookie
        return client


async def reset_client(platform: str):
    async with _lock:
        client = _clients.pop(platform, None)
        if client:
            await client.aclose()


async def save_account(platform: str, cookie: str) -> dict:
    """录入/更新账号：校验 Cookie 字段 → 探测昵称 → 加密落库。"""
    cls = CLIENT_CLASSES.get(platform)
    if not cls:
        raise ValueError(f"不支持的平台: {platform}")
    cookie = (cookie or "").strip().replace("\n", "")
    valid_fmt = cls.is_valid_cookie(cookie)
    nickname, valid = "", valid_fmt
    if valid_fmt:
        probe = cls(cookie=cookie)
        try:
            nickname = await probe.fetch_nickname()
        except Exception as e:
            logger.debug(f"{platform} 昵称探测失败: {e}")
            valid = False
        finally:
            await probe.aclose()
    async with async_session() as session:
        row = (await session.execute(
            select(AccountRow).where(AccountRow.platform == platform)
        )).scalar_one_or_none()
        if row is None:
            row = AccountRow(platform=platform)
            session.add(row)
        row.cookie = crypto.encrypt(cookie) if cookie else ""
        row.nickname = nickname or ""
        row.valid = 1 if valid else 0
        await session.commit()
    await reset_client(platform)
    return {"platform": platform, "label": cls.label, "nickname": nickname,
            "valid": valid, "has_cookie": bool(cookie)}


async def list_accounts() -> list[dict]:
    async with async_session() as session:
        rows = (await session.execute(select(AccountRow))).scalars().all()
    by_platform = {r.platform: r for r in rows}
    out = []
    for key, cls in CLIENT_CLASSES.items():
        row = by_platform.get(key)
        out.append({
            "platform": key, "label": cls.label,
            "has_cookie": bool(row and row.cookie),
            "nickname": (row.nickname if row else "") or "",
            "valid": bool(row and row.valid) if row and row.cookie else False,
            "login_required": not cls.GUEST_SUPPORTED,
            "guest_note": _guest_note(cls),
        })
    return out


def _guest_note(cls) -> str:
    if not cls.GUEST_SUPPORTED:
        return "下载/转存需登录账号"
    limit = getattr(cls, "GUEST_MAX_BYTES", 0)
    if limit:
        return f"未登录可直接播放约 {limit // 1024 // 1024}MB 以内的文件"
    return "未登录也可直接解析播放"


async def delete_account(platform: str) -> bool:
    from sqlalchemy import delete
    async with async_session() as session:
        await session.execute(delete(AccountRow).where(AccountRow.platform == platform))
        await session.commit()
    await reset_client(platform)
    return True


async def check_account(platform: str) -> dict:
    """登录态校验：refresh（触发 __puus 重下发）→ 拉昵称。"""
    cls = CLIENT_CLASSES.get(platform)
    if not cls:
        raise ValueError(f"不支持的平台: {platform}")
    client = await get_client(platform)
    if not client or not client.cookie:
        return {"platform": platform, "valid": False, "detail": "尚未录入 Cookie"}
    try:
        await client.refresh_session()
        nickname = await client.fetch_nickname()
    except Exception as e:
        nickname = ""
        detail = str(e)[:120]
        async with async_session() as session:
            row = (await session.execute(
                select(AccountRow).where(AccountRow.platform == platform)
            )).scalar_one_or_none()
            if row:
                row.valid = 0
                await session.commit()
        return {"platform": platform, "valid": False, "detail": detail}
    async with async_session() as session:
        row = (await session.execute(
            select(AccountRow).where(AccountRow.platform == platform)
        )).scalar_one_or_none()
        if row:
            row.valid = 1
            if nickname:
                row.nickname = nickname
            await session.commit()
    return {"platform": platform, "valid": True, "nickname": nickname, "detail": "登录态有效"}
