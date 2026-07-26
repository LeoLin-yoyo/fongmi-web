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


async def _get_enabled_configs():
    async with async_session() as session:
        result = await session.execute(
            select(ConfigModel).where(ConfigModel.enabled == 1).order_by(ConfigModel.priority.desc())
        )
        return result.scalars().all()


async def _fetch_url(url: str) -> str:
    client_kwargs = dict(timeout=15.0, verify=False, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    if _PROXY_URL:
        client_kwargs["proxy"] = _PROXY_URL
    async with httpx.AsyncClient(**client_kwargs) as client:
        resp = await client.get(url)
        return resp.text


@router.get("/groups")
async def live_groups():
    configs = await _get_enabled_configs()
    if not configs:
        return []

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
                })
        except Exception as e:
            logger.error(f"live_groups config {cfg.id} error: {e}")

    return all_lives


@router.get("/channels")
async def live_channels(source_idx: int = Query(default=0)):
    configs = await _get_enabled_configs()
    if not configs:
        return []

    all_lives = []
    for cfg in configs:
        try:
            data = json.loads(decrypt_config(cfg.content))
            lives = data.get("lives", [])
            for lv in lives:
                all_lives.append({"name": lv.get("name", ""), "url": lv.get("url", ""), "type": lv.get("type", 0), "_config_id": cfg.id})
        except Exception as e:
            logger.error(f"live_channels config {cfg.id} error: {e}")

    if source_idx >= len(all_lives):
        return []

    lv = all_lives[source_idx]
    url = lv.get("url", "")
    if not url:
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