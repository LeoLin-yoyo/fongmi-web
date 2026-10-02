"""Live TV API - M3U/TXT/JSON parsing with multi-line channel merging"""
import json
import re
import httpx
from fastapi import APIRouter, Query
from loguru import logger

from api.decoder import decrypt_config
from model.database import async_session, Config as ConfigModel
from sqlalchemy import select

router = APIRouter(prefix="/live", tags=["live"])

from spider.proxy_config import get_proxy_url

_PROXY_URL = get_proxy_url()
_CACHED_CONFIGS = None
_CACHED_CONFIGS_TIME = 0.0
_CONFIG_CACHE_TTL = 60  # 秒


async def _get_enabled_configs():
    global _CACHED_CONFIGS, _CACHED_CONFIGS_TIME
    import time
    now = time.time()
    if _CACHED_CONFIGS is not None and (now - _CACHED_CONFIGS_TIME) < _CONFIG_CACHE_TTL:
        return _CACHED_CONFIGS
    async with async_session() as session:
        result = await session.execute(
            select(ConfigModel).where(ConfigModel.enabled == 1).order_by(ConfigModel.priority.desc())
        )
        _CACHED_CONFIGS = result.scalars().all()
        _CACHED_CONFIGS_TIME = now
        return _CACHED_CONFIGS


async def _fetch_url(url: str) -> str:
    client_kwargs = dict(timeout=15.0, verify=False, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    if _PROXY_URL:
        client_kwargs["proxy"] = _PROXY_URL
    async with httpx.AsyncClient(**client_kwargs) as client:
        resp = await client.get(url)
        return resp.text


@router.get("/epg")
async def live_epg(source_idx: int = Query(default=0)):
    configs = await _get_enabled_configs()
    all_lives = []
    for cfg in configs:
        try:
            data = json.loads(decrypt_config(cfg.content))
            lives = data.get("lives", [])
            for lv in lives:
                all_lives.append({"name": lv.get("name", ""), "url": lv.get("url", ""), "epg": lv.get("epg", ""), "_config_id": cfg.id})
        except Exception as e:
            logger.error(f"live_epg config {cfg.id} error: {e}")

    if source_idx >= len(all_lives):
        return {"epg": []}

    lv = all_lives[source_idx]
    epg_url = lv.get("epg", "")
    if not epg_url:
        return {"epg": []}

    try:
        text = await _fetch_url(epg_url)
        # defusedxml 拒绝 DTD/实体定义，防 XML 实体扩展（billion laughs）
        from defusedxml import ElementTree as SafeET
        root = SafeET.fromstring(text)
        programs = []
        for prog in root.findall(".//programme"):
            ch_id = prog.get("channel", "")
            start = prog.get("start", "")
            stop = prog.get("stop", "")
            title_el = prog.find("title")
            desc_el = prog.find("desc")
            title = title_el.text if title_el is not None else ""
            desc = desc_el.text if desc_el is not None else ""
            programs.append({"channel": ch_id, "start": start, "stop": stop, "title": title, "desc": desc})
        return {"epg": programs}
    except Exception as e:
        logger.error(f"live_epg fetch error: {e}")
        return {"epg": []}


@router.get("/groups")
async def live_groups():
    configs = await _get_enabled_configs()

    all_lives = []
    for cfg in configs:
        try:
            data = json.loads(decrypt_config(cfg.content))
            lives = data.get("lives", [])
            for lv in lives:
                all_lives.append({
                    "name": lv.get("name", f"Source"),
                    "type": lv.get("type", 0),
                    "url": lv.get("url", ""),
                    "epg": lv.get("epg", ""),
                    "_config_id": cfg.id,
                    "_config_name": cfg.name,
                    "_source_type": "config",
                })
        except Exception as e:
            logger.error(f"live_groups config {cfg.id} error: {e}")

    # 合并直接导入的直播源
    from model.database import async_session, LiveSource as LiveSourceModel
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(LiveSourceModel).where(LiveSourceModel.enabled == 1).order_by(LiveSourceModel.priority.desc())
        )
        sources = result.scalars().all()
        for s in sources:
            all_lives.append({
                "name": s.name,
                "type": 0,
                "url": s.url,
                "epg": "",
                "_config_id": s.id,
                "_config_name": s.name,
                "_source_type": "direct",
                "_direct_id": s.id,
            })

    return all_lives


@router.get("/channels")
async def live_channels(source_idx: int = Query(default=0)):
    configs = await _get_enabled_configs()

    all_lives = []
    for cfg in configs:
        try:
            data = json.loads(decrypt_config(cfg.content))
            lives = data.get("lives", [])
            for lv in lives:
                all_lives.append({"name": lv.get("name", ""), "url": lv.get("url", ""), "type": lv.get("type", 0), "_config_id": cfg.id, "_source_type": "config"})
        except Exception as e:
            logger.error(f"live_channels config {cfg.id} error: {e}")

    # 合并直接导入的直播源
    from model.database import async_session, LiveSource as LiveSourceModel
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(LiveSourceModel).where(LiveSourceModel.enabled == 1).order_by(LiveSourceModel.priority.desc())
        )
        sources = result.scalars().all()
        for s in sources:
            all_lives.append({"name": s.name, "url": s.url, "type": 0, "_config_id": s.id, "_source_type": "direct"})

    if source_idx >= len(all_lives):
        return []

    lv = all_lives[source_idx]
    url = lv.get("url", "")
    if not url:
        return []

    if lv.get("_source_type") == "direct":
        from api.live_source import _parse_m3u_groups, _parse_json_groups, _parse_txt_groups
        try:
            text = await _fetch_url(url)
            if "#EXTM3U" in text or "#EXTINF" in text:
                return _parse_m3u_groups(text)
            elif text.strip().startswith("["):
                return _parse_json_groups(text)
            else:
                return _parse_txt_groups(text)
        except Exception as e:
            logger.error(f"live_channels direct fetch error: {e}")
            return []

    try:
        text = await _fetch_url(url)
        if text.strip().startswith("["):
            return _parse_json(text)
        elif "#EXTM3U" in text or "#EXTINF" in text:
            return _parse_m3u(text)
        else:
            return _parse_txt(text)
    except Exception as e:
        logger.error(f"live_channels fetch error: {e}")
        return []


def _parse_url_with_headers(raw_url: str) -> tuple:
    headers = {}
    url = raw_url.strip()
    if "|" in url:
        parts = url.split("|", 1)
        url = parts[0].strip()
        for pair in parts[1].split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                headers[k.strip()] = v.strip()
    return url, headers


def _merge_channel(name: str, raw_url: str, groups: dict, group_name: str, extra_headers: dict = None):
    url, inline_headers = _parse_url_with_headers(raw_url)
    if not url or "://" not in url:
        return
    merged = {**(extra_headers or {}), **inline_headers}
    if group_name not in groups:
        groups[group_name] = {}
    channels = groups[group_name]
    if name in channels:
        existing = channels[name]
        existing["urls"].append(url)
        existing["headers"].append(merged)
    else:
        channels[name] = {"name": name, "urls": [url], "headers": [merged], "current_index": 0}


def _parse_json(text: str) -> list:
    data = json.loads(text)
    result = []
    for group in data:
        group_name = group.get("name", "Default")
        channels = []
        for ch in group.get("channel", []):
            ch_name = ch.get("name", "Channel")
            urls = ch.get("urls", [])
            channel_data = {"name": ch_name, "urls": [], "headers": [], "current_index": 0}
            for url in urls:
                clean_url, headers = _parse_url_with_headers(url)
                channel_data["urls"].append(clean_url)
                channel_data["headers"].append(headers)
            channels.append(channel_data)
        result.append({"name": group_name, "channels": channels})
    return result


def _parse_m3u(text: str) -> list:
    groups = {}
    current_group = "Default"
    ch_name = ""
    extra_headers = {}

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        if line.startswith("#EXTINF:"):
            gt = re.search(r'group-title="([^"]*)"', line)
            if gt:
                current_group = gt.group(1)
            m = re.search(r',(.+?)$', line)
            if m:
                ch_name = m.group(1).strip()
            extra_headers = {}

        elif line.startswith("#EXTHTTP:"):
            try:
                hdrs = json.loads(line[len("#EXTHTTP:"):])
                if isinstance(hdrs, dict):
                    extra_headers.update(hdrs)
            except json.JSONDecodeError:
                pass

        elif line.startswith("#EXTVLCOPT:"):
            val = line[len("#EXTVLCOPT:"):].strip()
            if val.startswith("http-user-agent="):
                extra_headers["User-Agent"] = val.split("=", 1)[1].strip()
            elif val.startswith("http-referrer="):
                extra_headers["Referer"] = val.split("=", 1)[1].strip()
            elif val.startswith("http-origin="):
                extra_headers["Origin"] = val.split("=", 1)[1].strip()

        elif line.startswith("#KODIPROP:"):
            val = line[len("#KODIPROP:"):].strip()
            key = val.split("=", 1)[0].strip()
            value = val.split("=", 1)[1].strip() if "=" in val else ""
            extra_headers["#KODIPROP:" + key] = value

        elif line.startswith("ua="):
            extra_headers["User-Agent"] = line[3:].strip()
        elif line.startswith("referer="):
            extra_headers["Referer"] = line[8:].strip()
        elif line.startswith("referrer="):
            extra_headers["Referer"] = line[9:].strip()
        elif line.startswith("header="):
            try:
                raw = line[7:].strip()
                if raw.startswith("{"):
                    hdrs = json.loads(raw)
                    if isinstance(hdrs, dict):
                        extra_headers.update(hdrs)
            except json.JSONDecodeError:
                pass
        elif line.startswith("format="):
            extra_headers["format"] = line[7:].strip()
        elif line.startswith("parse="):
            extra_headers["parse"] = line[6:].strip()
        elif line.startswith("click="):
            extra_headers["click"] = line[6:].strip()

        elif line and not line.startswith("#") and "://" in line:
            _merge_channel(ch_name or "Channel", line, groups, current_group, extra_headers)

    return [{"name": g, "channels": list(c.values())} for g, c in groups.items()]


def _parse_txt(text: str) -> list:
    groups = {}
    current_group = "Default"
    extra_headers = {}

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        if "#genre#" in line:
            current_group = line.replace("#genre#", "").strip()
            extra_headers = {}
        elif line.startswith("ua="):
            extra_headers["User-Agent"] = line[3:].strip()
        elif line.startswith("referer="):
            extra_headers["Referer"] = line[8:].strip()
        elif line.startswith("referrer="):
            extra_headers["Referer"] = line[9:].strip()
        elif line.startswith("header="):
            try:
                raw = line[7:].strip()
                if raw.startswith("{"):
                    hdrs = json.loads(raw)
                    if isinstance(hdrs, dict):
                        extra_headers.update(hdrs)
            except json.JSONDecodeError:
                pass
        elif line.startswith("format="):
            extra_headers["format"] = line[7:].strip()
        elif line.startswith("parse="):
            extra_headers["parse"] = line[6:].strip()
        elif "," in line and "://" in line:
            parts = line.split(",", 1)
            if len(parts) == 2:
                name = parts[0].strip()
                for url in parts[1].split("#"):
                    _merge_channel(name, url, groups, current_group, extra_headers)

    return [{"name": g, "channels": list(c.values())} for g, c in groups.items()]