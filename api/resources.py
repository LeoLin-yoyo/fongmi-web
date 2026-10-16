"""资源索引 REST API（挂载于 /api/resources）。

- 索引管理：TG 频道 / 网盘分享目录 → 本地索引
- 索引统计与清空
- 资源详情与播放/下载直链签发（虚拟源结果点击后走这里）
"""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from resource_search import indexer, store
from resource_search.store import ResourceIndex

router = APIRouter(prefix="/resources", tags=["resources"])


class IndexTgRequest(BaseModel):
    peer: str
    limit: int = 200


class IndexPanRequest(BaseModel):
    platform: str
    share_id: str
    passcode: str = ""
    pdir_fid: str = "0"
    recursive: bool = True
    max_files: int = 500


@router.get("/stats")
async def stats():
    return {"code": 0, "data": await indexer.list_index_stats()}


@router.post("/index/tg")
async def index_tg(req: IndexTgRequest):
    if not req.peer.strip():
        raise HTTPException(400, "请提供 TG 频道（@username 或 id）")
    res = await indexer.index_tg_chats(req.peer.strip(), req.limit)
    if not res.get("ok"):
        raise HTTPException(422, res.get("detail") or "索引失败")
    return {"code": 0, "data": res}


@router.post("/index/pan")
async def index_pan(req: IndexPanRequest):
    res = await indexer.index_pan_folder(req.platform, req.share_id, req.passcode,
                                         req.pdir_fid, req.recursive, req.max_files)
    if not res.get("ok"):
        raise HTTPException(422, res.get("detail") or "索引失败")
    return {"code": 0, "data": res}


@router.delete("/index")
async def clear(kind: str = ""):
    n = await indexer.clear_index(kind)
    return {"code": 0, "cleared": n}


@router.get("/search")
async def search(wd: str, limit: int = 60):
    if not wd.strip():
        raise HTTPException(400, "关键词不能为空")
    return {"code": 0, "data": await indexer.search_resources(wd, limit)}


@router.get("/detail/{entry_id}")
async def detail(entry_id: int):
    row = await store.get_entry(entry_id)
    if not row:
        raise HTTPException(404, "资源不存在")
    return {"code": 0, "data": {
        "id": row.id, "kind": row.kind, "site_key": row.site_key,
        "name": row.name, "size": row.size,
        "payload": json.loads(row.payload or "{}"),
    }}


@router.post("/play/{entry_id}")
async def play(entry_id: int):
    """为索引条目签发播放地址。

    - pan 条目：走 pan 的直链签发 → 返回 /api/pan/stream/<token>
    - tg 条目：返回 /api/tg/stream/<sid>/<href>
    """
    row = await store.get_entry(entry_id)
    if not row:
        raise HTTPException(404, "资源不存在")
    payload = json.loads(row.payload or "{}")
    if row.kind == "tg":
        sid = payload.get("sid")
        href = payload.get("href")
        if not sid or not href:
            raise HTTPException(422, "TG 索引条目缺少会话信息，请重新索引")
        from tg.serve import serve_manager
        sess = serve_manager.get(sid)
        if not sess or sess.state != "ready":
            raise HTTPException(410, "TG 会话已关闭，请重新索引该频道")
        name = next((f["name"] for f in sess.files if f["href"] == href), row.name)
        return {"code": 0, "data": {"url": f"/api/tg/stream/{sid}/{href}",
                                    "name": name, "playable": True}}
    # pan
    from pan import resolver
    from pan.models import PanError, ShareFile
    try:
        f = ShareFile(fid=payload.get("fid", ""), fname=row.name, fsize=row.size,
                      fid_token=payload.get("fid_token", ""))
        link = await resolver.issue_link(payload.get("platform", ""),
                                         payload.get("share_id", ""),
                                         payload.get("passcode", ""), f)
    except PanError as e:
        raise HTTPException(422, f"取直链失败：{e}")
    from pan.api import _is_browser_playable
    return {"code": 0, "data": {"url": f"/api/pan/stream/{link.token}",
                                "name": link.filename, "size": link.size,
                                "playable": _is_browser_playable(link.filename)}}
