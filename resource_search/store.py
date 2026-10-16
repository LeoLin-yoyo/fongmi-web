"""资源索引存储（SQLAlchemy，挂现有 fongmi.db）。

一条索引记录 = 一个可播放/可下载的资源条目：
- kind: 'tg' | 'pan'
- site_key: 虚拟源标识（tg:<频道> / pan:<平台>），供 SearchPage 分 tab 与换源
- name: 片名（清洗后的标题）
- payload: JSON，含播放/下载所需的上下文（TG 的 link，网盘的 platform/share_id/fid 等）
"""
import json
import re
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, Text, DateTime

from model.database import Base, async_session


class ResourceIndex(Base):
    __tablename__ = "resource_index"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(8), default="tg", index=True)
    site_key: Mapped[str] = mapped_column(String(128), default="", index=True)
    site_name: Mapped[str] = mapped_column(String(255), default="")
    name: Mapped[str] = mapped_column(String(512), default="", index=True)
    name_norm: Mapped[str] = mapped_column(String(512), default="", index=True)
    pic: Mapped[str] = mapped_column(String(1024), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[str] = mapped_column(Text, default="")
    source_ref: Mapped[str] = mapped_column(String(512), default="", index=True)  # 去重键
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


_VIDEO_EXT = {"mp4", "mkv", "avi", "mov", "wmv", "flv", "ts", "rmvb", "webm", "m4v", "mpg", "mpeg", "m2ts"}


def normalize_name(name: str) -> str:
    """片名清洗：去扩展名、去季集/分辨率/编码噪声，供模糊匹配。"""
    n = (name or "").strip()
    # 先剥扩展名（在把点号转空格之前）
    n = re.sub(r"\.(mp4|mkv|avi|mov|wmv|flv|ts|rmvb|webm|m4v|mpg|mpeg|m2ts)$", "", n, flags=re.I)
    # 去掉常见画质/编码/发布标记（此时点号仍在，用 \b 边界匹配）
    n = re.sub(r"[.\_]", " ", n)
    n = re.sub(r"[\[\]\(\)【】]", " ", n)
    n = re.sub(r"\b(1080p|720p|2160p|4k|bluray|blu-ray|web-?dl|hdtv|hevc|x264|x265|h264|h265|aac|dts)\b",
               " ", n, flags=re.I)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def is_video(name: str) -> bool:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext in _VIDEO_EXT


async def upsert_entries(entries: list[dict]) -> int:
    """批量写入（按 source_ref 去重更新）。返回新增/更新条数。"""
    if not entries:
        return 0
    added = 0
    async with async_session() as session:
        for e in entries:
            ref = e.get("source_ref") or ""
            name = e.get("name") or ""
            norm = normalize_name(name)
            if not name:
                continue
            existing = None
            if ref:
                existing = (await session.execute(
                    select(ResourceIndex).where(ResourceIndex.source_ref == ref)
                )).scalar_one_or_none()
            if existing:
                existing.name = name
                existing.name_norm = norm
                existing.size = e.get("size") or 0
                existing.payload = json.dumps(e.get("payload") or {}, ensure_ascii=False)
                existing.pic = e.get("pic") or ""
            else:
                session.add(ResourceIndex(
                    kind=e.get("kind") or "tg",
                    site_key=e.get("site_key") or "",
                    site_name=e.get("site_name") or "",
                    name=name, name_norm=norm, pic=e.get("pic") or "",
                    size=e.get("size") or 0,
                    payload=json.dumps(e.get("payload") or {}, ensure_ascii=False),
                    source_ref=ref,
                ))
                added += 1
        await session.commit()
    return added


async def query(keyword: str, limit: int = 60) -> list[dict]:
    """关键词检索：先精确包含，再对清洗名做包含匹配。"""
    kw = (keyword or "").strip()
    if not kw:
        return []
    norm_kw = normalize_name(kw).lower()
    async with async_session() as session:
        rows = (await session.execute(
            select(ResourceIndex).where(
                ResourceIndex.name_norm.ilike(f"%{norm_kw}%")
            ).order_by(ResourceIndex.size.desc()).limit(limit)
        )).scalars().all()
    return [_to_vod(r) for r in rows]


def _to_vod(r: ResourceIndex) -> dict:
    """转成聚合搜索统一的 vod 形态（带 _site_key / _site_name，供 SearchPage 分 tab）。"""
    return {
        "vod_id": str(r.id),
        "vod_name": r.name,
        "vod_pic": r.pic,
        "vod_remarks": _fmt_size(r.size),
        "vod_year": "",
        "vod_area": "",
        "_site_key": r.site_key,
        "_site_name": r.site_name,
        "_kind": r.kind,
        "_payload": r.payload,
        "_resource_index_id": r.id,
    }


def _fmt_size(n: int) -> str:
    if not n:
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


async def stats() -> list[dict]:
    async with async_session() as session:
        rows = (await session.execute(
            select(ResourceIndex.site_key, ResourceIndex.site_name, func.count(ResourceIndex.id))
            .group_by(ResourceIndex.site_key, ResourceIndex.site_name)
        )).all()
    return [{"site_key": k, "site_name": n, "count": c} for k, n, c in rows]


async def clear(kind: str = "") -> int:
    async with async_session() as session:
        stmt = delete(ResourceIndex)
        if kind:
            stmt = stmt.where(ResourceIndex.kind == kind)
        result = await session.execute(stmt)
        await session.commit()
    return result.rowcount or 0


async def get_entry(entry_id: int) -> ResourceIndex | None:
    async with async_session() as session:
        return await session.get(ResourceIndex, entry_id)
