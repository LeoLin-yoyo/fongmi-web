"""History & Keep API"""
from datetime import datetime
from fastapi import APIRouter, Query, HTTPException

from model.database import async_session, History as HistoryModel, Keep as KeepModel
from model.bean import HistoryCreate, KeepCreate
from sqlalchemy import select, delete, desc, func


router = APIRouter()


@router.get("/history")
async def list_history(page: int = Query(default=1, ge=1), size: int = Query(default=50, ge=1, le=500)):
    async with async_session() as session:
        count_result = await session.execute(select(func.count(HistoryModel.id)))
        total = count_result.scalar() or 0
        result = await session.execute(
            select(HistoryModel).order_by(desc(HistoryModel.created_at)).offset((page - 1) * size).limit(size)
        )
        items = result.scalars().all()
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [
            {"id": h.id, "site_key": h.site_key, "vod_id": h.vod_id, "name": h.name,
             "pic": h.pic, "episode": h.episode, "position": h.position, "duration": h.duration,
             "time": h.created_at.isoformat() if h.created_at else ""}
            for h in items
        ]
    }


@router.get("/history/check")
async def check_history(site_key: str = Query(...), vod_id: str = Query(...)):
    async with async_session() as session:
        result = await session.execute(
            select(HistoryModel).where(HistoryModel.site_key == site_key, HistoryModel.vod_id == vod_id)
        )
        h = result.scalar_one_or_none()
    if h:
        return {"found": True, "id": h.id, "site_key": h.site_key, "vod_id": h.vod_id,
                "name": h.name, "episode": h.episode, "position": h.position, "duration": h.duration}
    return {"found": False}


@router.post("/history")
async def add_history(body: HistoryCreate):
    if not body.site_key or not body.vod_id:
        raise HTTPException(status_code=400, detail="site_key and vod_id are required")
    async with async_session() as session:
        result = await session.execute(
            select(HistoryModel).where(HistoryModel.site_key == body.site_key, HistoryModel.vod_id == body.vod_id)
        )
        existing = result.scalar_one_or_none()
        now = datetime.now()
        if existing:
            existing.name = body.name
            existing.pic = body.pic
            existing.episode = body.episode
            if body.position:
                existing.position = body.position
            if body.duration:
                existing.duration = body.duration
            existing.created_at = now
        else:
            session.add(HistoryModel(site_key=body.site_key, vod_id=body.vod_id, name=body.name,
                                     pic=body.pic, episode=body.episode, position=body.position,
                                     duration=body.duration, created_at=now))
        await session.commit()
    return {"code": 0}


@router.put("/history")
async def update_history(body: HistoryCreate):
    if not body.site_key or not body.vod_id:
        raise HTTPException(status_code=400, detail="site_key and vod_id are required")
    async with async_session() as session:
        result = await session.execute(
            select(HistoryModel).where(HistoryModel.site_key == body.site_key, HistoryModel.vod_id == body.vod_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.position = body.position
            existing.duration = body.duration
            existing.updated_at = datetime.now()
            await session.commit()
    return {"code": 0}


@router.delete("/history/cleanup")
async def cleanup_history():
    """删除 site_key 或 vod_id 为空的无效记录"""
    async with async_session() as session:
        result = await session.execute(
            delete(HistoryModel).where(
                (HistoryModel.site_key == "") | (HistoryModel.vod_id == "")
            )
        )
        await session.commit()
    return {"code": 0, "deleted": result.rowcount}


@router.delete("/history/{history_id}")
async def delete_history(history_id: int):
    async with async_session() as session:
        await session.execute(delete(HistoryModel).where(HistoryModel.id == history_id))
        await session.commit()
    return {"code": 0}


@router.delete("/history")
async def clear_history():
    async with async_session() as session:
        await session.execute(delete(HistoryModel))
        await session.commit()
    return {"code": 0}


@router.get("/keep")
async def list_keep(page: int = Query(default=1, ge=1), size: int = Query(default=50, ge=1, le=500)):
    async with async_session() as session:
        count_result = await session.execute(select(func.count(KeepModel.id)))
        total = count_result.scalar() or 0
        result = await session.execute(
            select(KeepModel).order_by(desc(KeepModel.created_at)).offset((page - 1) * size).limit(size)
        )
        items = result.scalars().all()
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [
            {"id": k.id, "site_key": k.site_key, "vod_id": k.vod_id, "name": k.name,
             "pic": k.pic, "type": k.type, "time": k.created_at.isoformat() if k.created_at else ""}
            for k in items
        ]
    }


@router.post("/keep")
async def add_keep(body: KeepCreate):
    if not body.site_key or not body.vod_id:
        raise HTTPException(status_code=400, detail="site_key and vod_id are required")
    async with async_session() as session:
        result = await session.execute(
            select(KeepModel).where(KeepModel.site_key == body.site_key, KeepModel.vod_id == body.vod_id)
        )
        if result.scalar_one_or_none():
            return {"code": 0, "msg": "already_keep"}
        session.add(KeepModel(site_key=body.site_key, vod_id=body.vod_id, name=body.name,
                              pic=body.pic, type=body.type, created_at=datetime.now()))
        await session.commit()
    return {"code": 0}


@router.delete("/keep/cleanup")
async def cleanup_keep():
    """删除 site_key 或 vod_id 为空的无效收藏"""
    async with async_session() as session:
        result = await session.execute(
            delete(KeepModel).where(
                (KeepModel.site_key == "") | (KeepModel.vod_id == "")
            )
        )
        await session.commit()
    return {"code": 0, "deleted": result.rowcount}


@router.delete("/keep/{keep_id}")
async def delete_keep(keep_id: int):
    async with async_session() as session:
        await session.execute(delete(KeepModel).where(KeepModel.id == keep_id))
        await session.commit()
    return {"code": 0}


@router.get("/keep/check")
async def check_keep(site_key: str = Query(...), vod_id: str = Query(...)):
    async with async_session() as session:
        result = await session.execute(
            select(KeepModel).where(KeepModel.site_key == site_key, KeepModel.vod_id == vod_id)
        )
        exists = result.scalar_one_or_none() is not None
    return {"is_keep": exists}