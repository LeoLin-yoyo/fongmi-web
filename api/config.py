import hashlib
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Body
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from pydantic import BaseModel
from typing import List

from api.decoder import decrypt_config
from model.database import get_db, Config as ConfigModel, Site as SiteModel, Parse as ParseModel
from model.bean import VodConfig, ConfigImportRequest


class BatchImportRequest(BaseModel):
    urls: List[str]


class ReorderRequest(BaseModel):
    ids: List[int]


class CheckUrlRequest(BaseModel):
    url: str


class CheckBatchRequest(BaseModel):
    urls: List[str]


class PriorityRequest(BaseModel):
    priority: int

router = APIRouter()


def compute_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def parse_config(data: dict) -> VodConfig:
    return VodConfig(**data)


def _fetch_html_config_urls(html: str) -> list[str]:
    """从 HTML 页面中提取可能的配置链接"""
    import re
    urls = []
    for match in re.finditer(r'https?://[^\s"\'<>]+', html):
        url = match.group(0).rstrip("/.,;:!?")
        if any(kw in url.lower() for kw in ["config", "json", "tv", "vod", "spider", "subscribe", "sub"]):
            urls.append(url)
    return urls


@router.get("/")
async def list_configs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ConfigModel).order_by(ConfigModel.priority.desc(), ConfigModel.id.desc()))
    configs = result.scalars().all()
    return {
        "code": 0,
        "data": [
            {
                "id": c.id,
                "name": c.name,
                "url": c.url,
                "type": c.type,
                "hash": c.hash,
                "enabled": c.enabled,
                "priority": c.priority,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in configs
        ],
    }


@router.post("/import")
async def import_config(
    request: Request,
    url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    json_str: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            json_body = json.loads(body)
            url = url or json_body.get("url")
            json_str = json_str or json_body.get("content") or json_body.get("json_str")
        except Exception:
            pass
    raw_content = ""

    if url:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, verify=False) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            raw_content = resp.text
    elif file:
        raw_content = (await file.read()).decode("utf-8")
    elif json_str:
        raw_content = json_str
    else:
        raise HTTPException(status_code=400, detail="Must provide url, file, or json")

    if not raw_content.strip():
        raise HTTPException(status_code=400, detail="Empty content")

    # 检测是否为 HTML 页面（非直接配置）
    is_html = raw_content.strip().startswith("<!DOCTYPE") or raw_content.strip().startswith("<html")
    if is_html:
        urls = _fetch_html_config_urls(raw_content)
        if urls:
            raise HTTPException(
                status_code=400,
                detail=f"链接返回的是 HTML 页面，非直接配置。可能的目标链接: {', '.join(urls[:3])}",
            )
        raise HTTPException(status_code=400, detail="链接返回的是 HTML 页面，无法解析为配置")

    try:
        decrypted = decrypt_config(raw_content)
        # 使用 strict=False 允许字符串值中包含原始换行等控制字符
        data = json.loads(decrypted, strict=False)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON 格式错误，请检查配置内容")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"解密失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"配置解析失败: {str(e)}")

    # 检测多仓格式（urls 数组，每个元素有 name + url）
    if isinstance(data, dict) and "urls" in data and isinstance(data["urls"], list) and not data.get("sites"):
        sub_urls = [u["url"] for u in data["urls"] if isinstance(u, dict) and u.get("url")]
        if sub_urls:
            raise HTTPException(
                status_code=400,
                detail=f"检测到多仓格式，包含 {len(sub_urls)} 个子配置链接。请使用批量导入单独导入各子链接，或使用 /api/config/import_batch 导入全部。",
            )

    cfg = await parse_config(data)
    cfg_hash = compute_hash(raw_content)

    existing = await db.execute(select(ConfigModel).where(ConfigModel.hash == cfg_hash))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Config already exists")

    name = data.get("name", "") or data.get("wall", "") or "Imported Config"
    config_type = "vod"
    if not cfg.sites and cfg.lives:
        config_type = "live"

    # 获取当前最大 priority
    max_p_result = await db.execute(select(ConfigModel).order_by(ConfigModel.priority.desc()).limit(1))
    max_p = max_p_result.scalar_one_or_none()
    next_priority = (max_p.priority + 1) if max_p else 0

    config_entry = ConfigModel(
        name=name,
        url=url or "",
        type=config_type,
        content=raw_content,
        hash=cfg_hash,
        enabled=1,
        priority=next_priority,
    )
    db.add(config_entry)
    await db.flush()

    for site in cfg.sites:
        site_entry = SiteModel(
            config_id=config_entry.id,
            key=site.key,
            name=site.name,
            type=site.type,
            api=site.api,
            ext=site.get_ext_str(),
            player_type=site.playerType,
            searchable=site.searchable,
            quick_search=site.quickSearch,
            filterable=site.filterable,
        )
        db.add(site_entry)

    for parse in cfg.parses:
        parse_entry = ParseModel(
            config_id=config_entry.id,
            name=parse.name,
            url=parse.url,
            type=parse.type,
            ext=json.dumps(parse.ext, ensure_ascii=False) if isinstance(parse.ext, dict) else str(parse.ext),
        )
        db.add(parse_entry)

    await db.commit()

    return {
        "code": 0,
        "config_id": config_entry.id,
        "site_count": len(cfg.sites),
        "live_count": len(cfg.lives),
        "parse_count": len(cfg.parses),
    }


@router.post("/import_batch")
async def import_configs(body: BatchImportRequest, db: AsyncSession = Depends(get_db)):
    """批量导入多个 URL，自动检测可用性，不可用的跳过"""
    results = []
    for url in body.urls:
        url = url.strip()
        if not url:
            continue

        # 先检测可用性
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True, verify=False) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                raw_content = resp.text
        except httpx.TimeoutException:
            results.append({"url": url, "status": "skipped", "detail": "Connection timeout, skipped"})
            continue
        except httpx.ConnectError:
            results.append({"url": url, "status": "skipped", "detail": "Connection refused, skipped"})
            continue
        except httpx.HTTPStatusError as e:
            results.append({"url": url, "status": "skipped", "detail": f"HTTP {e.response.status_code}, skipped"})
            continue
        except Exception as e:
            results.append({"url": url, "status": "skipped", "detail": f"Network error: {str(e)[:50]}, skipped"})
            continue

        if not raw_content.strip():
            results.append({"url": url, "status": "skipped", "detail": "Empty content, skipped"})
            continue

        if raw_content.strip().startswith("<!DOCTYPE") or raw_content.strip().startswith("<html"):
            results.append({"url": url, "status": "skipped", "detail": "HTML page, skipped"})
            continue

        try:
            decrypted = decrypt_config(raw_content)
            data = json.loads(decrypted)

            # 多仓格式：提取子链接并递归导入
            if isinstance(data, dict) and "urls" in data and isinstance(data["urls"], list) and not data.get("sites"):
                sub_urls = [u["url"] for u in data["urls"] if isinstance(u, dict) and u.get("url")]
                if sub_urls:
                    sub_results = []
                    for sub_url in sub_urls:
                        try:
                            async with httpx.AsyncClient(timeout=15, follow_redirects=True, verify=False) as client:
                                sub_resp = await client.get(sub_url)
                                sub_resp.raise_for_status()
                                sub_raw = sub_resp.text
                            sub_decrypted = decrypt_config(sub_raw)
                            sub_data = json.loads(sub_decrypted)
                            sub_cfg = await parse_config(sub_data)
                            sub_hash = compute_hash(sub_raw)
                            sub_existing = await db.execute(select(ConfigModel).where(ConfigModel.hash == sub_hash))
                            if sub_existing.scalar_one_or_none():
                                sub_results.append({"url": sub_url, "status": "skipped", "detail": "Already exists"})
                                continue
                            sub_name = sub_data.get("name", "") or sub_data.get("wall", "") or sub_url
                            sub_config_type = "vod"
                            if not sub_cfg.sites and sub_cfg.lives:
                                sub_config_type = "live"
                            if not sub_cfg.sites and not sub_cfg.lives:
                                sub_results.append({"url": sub_url, "status": "skipped", "detail": "No sites/lives"})
                                continue
                            max_p_result = await db.execute(select(ConfigModel).order_by(ConfigModel.priority.desc()).limit(1))
                            max_p = max_p_result.scalar_one_or_none()
                            next_priority = (max_p.priority + 1) if max_p else 0
                            sub_entry = ConfigModel(name=sub_name, url=sub_url, type=sub_config_type, content=sub_raw, hash=sub_hash, enabled=1, priority=next_priority)
                            db.add(sub_entry)
                            await db.flush()
                            for s in sub_cfg.sites:
                                db.add(SiteModel(config_id=sub_entry.id, key=s.key, name=s.name, type=s.type, api=s.api, ext=s.get_ext_str(), player_type=s.playerType, searchable=s.searchable, quick_search=s.quickSearch, filterable=s.filterable))
                            for p in sub_cfg.parses:
                                db.add(ParseModel(config_id=sub_entry.id, name=p.name, url=p.url, type=p.type, ext=json.dumps(p.ext, ensure_ascii=False) if isinstance(p.ext, dict) else str(p.ext)))
                            await db.commit()
                            sub_results.append({"url": sub_url, "status": "success", "site_count": len(sub_cfg.sites), "detail": ""})
                        except Exception as sub_e:
                            sub_results.append({"url": sub_url, "status": "skipped", "detail": str(sub_e)[:80]})
                    results.append({"url": url, "status": "success", "detail": f"多仓: {len(sub_results)} 个子链接", "sub_results": sub_results})
                    continue

            cfg = await parse_config(data)
            cfg_hash = compute_hash(raw_content)

            existing = await db.execute(select(ConfigModel).where(ConfigModel.hash == cfg_hash))
            if existing.scalar_one_or_none():
                results.append({"url": url, "status": "skipped", "detail": "Already exists"})
                continue

            name = data.get("name", "") or data.get("wall", "") or url
            config_type = "vod"
            if not cfg.sites and cfg.lives:
                config_type = "live"

            if not cfg.sites and not cfg.lives:
                results.append({"url": url, "status": "skipped", "detail": "No sites or lives, skipped"})
                continue

            max_p_result = await db.execute(select(ConfigModel).order_by(ConfigModel.priority.desc()).limit(1))
            max_p = max_p_result.scalar_one_or_none()
            next_priority = (max_p.priority + 1) if max_p else 0

            config_entry = ConfigModel(name=name, url=url, type=config_type, content=raw_content, hash=cfg_hash, enabled=1, priority=next_priority)
            db.add(config_entry)
            await db.flush()

            for site in cfg.sites:
                db.add(SiteModel(config_id=config_entry.id, key=site.key, name=site.name, type=site.type, api=site.api, ext=site.get_ext_str(), player_type=site.playerType, searchable=site.searchable, quick_search=site.quickSearch, filterable=site.filterable))

            for parse in cfg.parses:
                db.add(ParseModel(config_id=config_entry.id, name=parse.name, url=parse.url, type=parse.type, ext=json.dumps(parse.ext, ensure_ascii=False) if isinstance(parse.ext, dict) else str(parse.ext)))

            await db.commit()
            results.append({"url": url, "status": "success", "site_count": len(cfg.sites), "detail": ""})
        except json.JSONDecodeError:
            results.append({"url": url, "status": "skipped", "detail": "JSON parse failed, skipped"})
        except Exception as e:
            results.append({"url": url, "status": "error", "detail": str(e)})

    return {"code": 0, "results": results}


@router.post("/check_url")
async def check_url(body: CheckUrlRequest):
    """检查单个订阅源 URL 是否可用"""
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is empty")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, verify=False) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            raw_content = resp.text
        if not raw_content.strip():
            return {"code": 1, "available": False, "detail": "Empty content"}
        is_html = raw_content.strip().startswith("<!DOCTYPE") or raw_content.strip().startswith("<html")
        if is_html:
            return {"code": 1, "available": False, "detail": "URL returns HTML page, not a config"}
        try:
            decrypted = decrypt_config(raw_content)
            data = json.loads(decrypted)
            has_sites = len(data.get("sites", [])) > 0
            has_lives = len(data.get("lives", [])) > 0
            if not has_sites and not has_lives:
                return {"code": 1, "available": False, "detail": "Config has no sites or lives"}
            return {
                "code": 0,
                "available": True,
                "detail": "OK",
                "name": data.get("name", "") or data.get("wall", "") or "",
                "site_count": len(data.get("sites", [])),
                "live_count": len(data.get("lives", [])),
                "parse_count": len(data.get("parses", [])),
                "is_vod": has_sites,
                "is_live": has_lives and not has_sites,
            }
        except (json.JSONDecodeError, ValueError) as e:
            return {"code": 1, "available": False, "detail": f"Parse failed: {str(e)}"}
    except httpx.TimeoutException:
        return {"code": 1, "available": False, "detail": "Connection timeout"}
    except httpx.ConnectError:
        return {"code": 1, "available": False, "detail": "Connection refused"}
    except httpx.HTTPStatusError as e:
        return {"code": 1, "available": False, "detail": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"code": 1, "available": False, "detail": str(e)}


@router.post("/check_batch")
async def check_batch(body: CheckBatchRequest):
    """批量检查多个订阅源 URL 是否可用"""
    import asyncio
    async def check_one(url: str):
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True, verify=False) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                raw_content = resp.text
            if not raw_content.strip():
                return {"url": url, "available": False, "detail": "Empty content"}
            is_html = raw_content.strip().startswith("<!DOCTYPE") or raw_content.strip().startswith("<html")
            if is_html:
                return {"url": url, "available": False, "detail": "HTML page"}
            decrypted = decrypt_config(raw_content)
            data = json.loads(decrypted)
            # 多仓格式
            if isinstance(data, dict) and "urls" in data and isinstance(data["urls"], list) and not data.get("sites"):
                sub_urls = [u["url"] for u in data["urls"] if isinstance(u, dict) and u.get("url")]
                return {
                    "url": url,
                    "available": True,
                    "detail": f"多仓格式, {len(sub_urls)} 子链接",
                    "name": data.get("name", "") or "",
                    "site_count": 0,
                    "live_count": 0,
                    "is_multi_warehouse": True,
                    "sub_urls": sub_urls,
                }
            has_sites = len(data.get("sites", [])) > 0
            has_lives = len(data.get("lives", [])) > 0
            return {
                "url": url,
                "available": has_sites or has_lives,
                "detail": "OK" if (has_sites or has_lives) else "No sites/lives",
                "name": data.get("name", "") or data.get("wall", "") or "",
                "site_count": len(data.get("sites", [])),
                "live_count": len(data.get("lives", [])),
            }
        except Exception as e:
            return {"url": url, "available": False, "detail": str(e)}

    tasks = [check_one(url.strip()) for url in body.urls if url.strip()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    final = []
    for r in results:
        if isinstance(r, Exception):
            final.append({"url": "", "available": False, "detail": str(r)})
        else:
            final.append(r)
    return {"code": 0, "results": final}


@router.delete("/{config_id}")
async def delete_config(config_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ConfigModel).where(ConfigModel.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    await db.execute(delete(SiteModel).where(SiteModel.config_id == config_id))
    await db.execute(delete(ParseModel).where(ParseModel.config_id == config_id))
    await db.delete(config)
    await db.commit()
    return {"code": 0}


@router.put("/{config_id}/toggle")
async def toggle_config(config_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ConfigModel).where(ConfigModel.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    config.enabled = 0 if config.enabled else 1
    await db.commit()
    return {"code": 0, "enabled": config.enabled}


@router.put("/{config_id}/priority")
async def set_priority(config_id: int, body: PriorityRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ConfigModel).where(ConfigModel.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    config.priority = body.priority
    await db.commit()
    return {"code": 0, "priority": config.priority}


@router.put("/reorder")
async def reorder_configs(body: ReorderRequest, db: AsyncSession = Depends(get_db)):
    """批量重排优先级（ids 顺序决定优先级，越靠前优先级越高）"""
    for i, config_id in enumerate(body.ids):
        await db.execute(update(ConfigModel).where(ConfigModel.id == config_id).values(priority=len(body.ids) - i))
    await db.commit()
    return {"code": 0}


@router.get("/site/")
async def list_sites(db: AsyncSession = Depends(get_db)):
    """返回所有 enabled 配置的站点，按 key 去重（取 priority 最高的）"""
    configs = await db.execute(select(ConfigModel).where(ConfigModel.enabled == 1).order_by(ConfigModel.priority.desc()))
    enabled_configs = configs.scalars().all()
    if not enabled_configs:
        return {"code": 0, "data": []}

    seen_keys = set()
    merged = []
    for cfg in enabled_configs:
        site_result = await db.execute(
            select(SiteModel).where(SiteModel.config_id == cfg.id)
        )
        sites = site_result.scalars().all()
        for s in sites:
            if s.key not in seen_keys:
                seen_keys.add(s.key)
                merged.append({
                    "id": s.id,
                    "key": s.key,
                    "name": s.name,
                    "type": s.type,
                    "api": s.api,
                    "ext": s.ext,
                    "player_type": s.player_type,
                    "searchable": s.searchable,
                    "quick_search": s.quick_search,
                    "filterable": s.filterable,
                    "_config_id": cfg.id,
                    "_config_name": cfg.name,
                })
    return {"code": 0, "data": merged}


@router.get("/parses/")
async def list_parses(db: AsyncSession = Depends(get_db)):
    """返回所有 enabled 配置的解析器，去重"""
    configs = await db.execute(select(ConfigModel).where(ConfigModel.enabled == 1).order_by(ConfigModel.priority.desc()))
    enabled_configs = configs.scalars().all()
    if not enabled_configs:
        return {"code": 0, "data": []}

    seen = set()
    merged = []
    for cfg in enabled_configs:
        parse_result = await db.execute(
            select(ParseModel).where(ParseModel.config_id == cfg.id)
        )
        parses = parse_result.scalars().all()
        for p in parses:
            key = (p.url, p.type)
            if key not in seen:
                seen.add(key)
                merged.append({"name": p.name, "url": p.url, "type": p.type, "ext": p.ext})
    return {"code": 0, "data": merged}