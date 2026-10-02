"""Direct Live Source API - import m3u/txt URLs directly"""
import json
import re
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from loguru import logger

from model.database import get_db, LiveSource as LiveSourceModel
from spider.proxy_config import get_proxy_url

router = APIRouter(tags=["live_source"])

_PROXY_URL = get_proxy_url()


class ImportLiveSourceRequest(BaseModel):
    url: str
    name: str = ""


class ImportBatchLiveRequest(BaseModel):
    items: list[ImportLiveSourceRequest]


@router.get("/")
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LiveSourceModel).order_by(LiveSourceModel.priority.desc(), LiveSourceModel.id.desc()))
    sources = result.scalars().all()
    return {
        "code": 0,
        "data": [
            {
                "id": s.id,
                "name": s.name,
                "url": s.url,
                "type": s.type,
                "enabled": s.enabled,
                "priority": s.priority,
                "group_count": s.group_count,
                "channel_count": s.channel_count,
            }
            for s in sources
        ],
    }


@router.post("/import")
async def import_live_source(body: ImportLiveSourceRequest, db: AsyncSession = Depends(get_db)):
    url = body.url.strip()
    if not url:
        raise HTTPException(400, "URL is empty")

    client_kwargs = dict(timeout=15, verify=False, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    if _PROXY_URL:
        client_kwargs["proxy"] = _PROXY_URL

    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text
    except Exception as e:
        raise HTTPException(400, f"Fetch failed: {str(e)[:100]}")

    if not text.strip():
        raise HTTPException(400, "Empty content")

    source_type = "m3u"
    groups = []
    channels_count = 0

    if "#EXTM3U" in text or "#EXTINF" in text:
        groups, channels_count = _parse_m3u_preview(text)
        source_type = "m3u"
    elif text.strip().startswith("["):
        try:
            data = json.loads(text)
            groups = [g.get("name", "Default") for g in data]
            channels_count = sum(len(g.get("channels", [])) for g in data)
            source_type = "json"
        except json.JSONDecodeError:
            pass
    else:
        groups, channels_count = _parse_txt_preview(text)
        source_type = "txt"

    if channels_count == 0:
        raise HTTPException(400, "No channels found in the content")

    max_p_result = await db.execute(select(LiveSourceModel).order_by(LiveSourceModel.priority.desc()).limit(1))
    max_p = max_p_result.scalar_one_or_none()
    next_priority = (max_p.priority + 1) if max_p else 0

    name = body.name or url.split("/")[-1].split("?")[0] or "Live Source"
    entry = LiveSourceModel(
        name=name,
        url=url,
        type=source_type,
        enabled=1,
        priority=next_priority,
        group_count=len(groups),
        channel_count=channels_count,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    return {
        "code": 0,
        "id": entry.id,
        "name": name,
        "type": source_type,
        "group_count": len(groups),
        "channel_count": channels_count,
    }


@router.post("/import_batch")
async def import_batch(body: ImportBatchLiveRequest, db: AsyncSession = Depends(get_db)):
    results = []
    for item in body.items:
        try:
            req = ImportLiveSourceRequest(url=item.url, name=item.name)
            res = await import_live_source(req, db)
            results.append({"url": item.url, "status": "success", "detail": f"{res['channel_count']} channels"})
        except HTTPException as e:
            results.append({"url": item.url, "status": "skipped", "detail": e.detail})
        except Exception as e:
            results.append({"url": item.url, "status": "error", "detail": str(e)[:100]})
    return {"code": 0, "results": results}


@router.delete("/{source_id}")
async def delete_source(source_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LiveSourceModel).where(LiveSourceModel.id == source_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Source not found")
    await db.delete(entry)
    await db.commit()
    return {"code": 0}


@router.put("/{source_id}/toggle")
async def toggle_source(source_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LiveSourceModel).where(LiveSourceModel.id == source_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Source not found")
    entry.enabled = 0 if entry.enabled else 1
    await db.commit()
    return {"code": 0, "enabled": entry.enabled}


@router.get("/channels")
async def get_channels(source_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LiveSourceModel).where(LiveSourceModel.id == source_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Source not found")

    client_kwargs = dict(timeout=15, verify=False, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    if _PROXY_URL:
        client_kwargs["proxy"] = _PROXY_URL

    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.get(entry.url)
            text = resp.text
    except Exception as e:
        raise HTTPException(400, f"Fetch failed: {str(e)[:100]}")

    if "#EXTM3U" in text or "#EXTINF" in text:
        return _parse_m3u_groups(text)
    elif text.strip().startswith("["):
        return _parse_json_groups(text)
    else:
        return _parse_txt_groups(text)


def _parse_m3u_preview(text: str):
    groups = set()
    count = 0
    for line in text.split("\n"):
        line = line.strip()
        if "#EXTINF:" in line:
            gt = re.search(r'group-title="([^"]*)"', line)
            if gt:
                groups.add(gt.group(1))
            count += 1
        elif line and not line.startswith("#") and "://" in line:
            pass
    return list(groups), count


def _parse_txt_preview(text: str):
    groups = set()
    count = 0
    for line in text.split("\n"):
        line = line.strip()
        if "#genre#" in line:
            groups.add(line.replace("#genre#", "").strip())
        elif "," in line and "://" in line:
            count += 1
    return list(groups), count


def _parse_m3u_groups(text: str):
    from api.live import _parse_m3u
    return _parse_m3u(text)


def _parse_json_groups(text: str):
    try:
        data = json.loads(text)
        return data
    except json.JSONDecodeError:
        return []


def _parse_txt_groups(text: str):
    from api.live import _parse_txt
    return _parse_txt(text)