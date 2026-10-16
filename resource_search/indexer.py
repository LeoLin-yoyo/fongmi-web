"""资源索引编排：从 TG 频道 / 网盘目录抓取条目并写入索引。"""
from loguru import logger

from . import store


async def index_tg_chats(peer: str, limit: int = 200) -> dict:
    """索引一个 TG 频道的消息文件（通过 tdl serve 列出文件清单）。

    peer 支持 @username / 频道 id；用 tdl serve 列文件（复用 TG 模块的 serve 会话）。
    """
    from tg.config import get_config
    from tg.serve import serve_manager
    from downloader.config import get_download_dir
    import os

    cfg = get_config()
    out_dir = cfg.download_dir or get_download_dir()
    os.makedirs(out_dir, exist_ok=True)
    # 构造该频道的 t.me 链接（tdl 支持按频道列出）
    url = peer if peer.startswith("http") else f"https://t.me/{peer.lstrip('@')}"
    try:
        sess = await serve_manager.start([url], out_dir)
    except Exception as e:
        return {"ok": False, "detail": f"启动 tdl serve 失败：{str(e)[:120]}"}
    if sess.state != "ready":
        await serve_manager.stop(sess.sid)
        return {"ok": False, "detail": sess.error or "tdl serve 未就绪"}

    entries = []
    for f in sess.files[:limit]:
        if not store.is_video(f["name"]):
            continue
        entries.append({
            "kind": "tg", "site_key": f"tg:{peer}", "site_name": f"TG·{peer}",
            "name": f["name"], "size": f["size"],
            "payload": {"sid": sess.sid, "href": f["href"], "peer": peer},
            "source_ref": f"tg:{peer}:{f['href']}",
        })
    # 注意：serve 会话保留在内存中（供后续播放）；此处不 stop，交由会话清理策略
    added = await store.upsert_entries(entries)
    logger.info(f"索引 TG 频道 {peer}: 新增 {added} / 共 {len(entries)} 条")
    return {"ok": True, "sid": sess.sid, "total": len(entries), "added": added}


async def index_pan_folder(platform: str, share_id: str, passcode: str = "",
                           pdir_fid: str = "0", recursive: bool = True,
                           max_files: int = 500) -> dict:
    """索引一个网盘分享目录（递归收集文件）。"""
    from pan import resolver
    from pan.models import PanError

    entries: list[dict] = []

    async def walk(fid: str, depth: int):
        if depth > 6 or len(entries) >= max_files:
            return
        try:
            files = await resolver.list_dir(platform, share_id, passcode, fid)
        except PanError as e:
            raise e
        for f in files:
            if len(entries) >= max_files:
                return
            if f.isdir:
                if recursive:
                    await walk(f.fid, depth + 1)
            elif store.is_video(f.fname):
                entries.append({
                    "kind": "pan", "site_key": f"pan:{platform}",
                    "site_name": f"网盘·{platform}",
                    "name": f.fname, "size": f.fsize,
                    "payload": {"platform": platform, "share_id": share_id,
                                "passcode": passcode, "fid": f.fid, "fid_token": f.fid_token},
                    "source_ref": f"pan:{platform}:{share_id}:{f.fid}",
                })

    try:
        await walk(pdir_fid, 1)
    except PanError as e:
        return {"ok": False, "detail": str(e)[:160]}
    added = await store.upsert_entries(entries)
    return {"ok": True, "total": len(entries), "added": added}


async def search_resources(keyword: str, limit: int = 60) -> dict:
    """聚合搜索接口：返回 {merged, per_site}（与 spider.search 同形）。"""
    items = await store.query(keyword, limit=limit)
    merged = []
    per_site: dict[str, dict] = {}
    for it in items:
        merged.append(it)
        sk = it["_site_key"]
        if sk not in per_site:
            per_site[sk] = {"name": it["_site_name"], "results": []}
        per_site[sk]["results"].append(it)
    return {"merged": merged, "per_site": per_site}


async def list_index_stats() -> list[dict]:
    return await store.stats()


async def clear_index(kind: str = "") -> int:
    return await store.clear(kind)
