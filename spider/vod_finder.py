"""Detect and cache which sites are real VOD (not live)"""
import json
from loguru import logger

from spider.http_sync import http_get_sync

_VOD_SITES_CACHE = []


def get_vod_sites_cache():
    return _VOD_SITES_CACHE


async def refresh_vod_sites():
    """Check which type=1 sites return actual VOD content"""
    global _VOD_SITES_CACHE

    import sqlite3
    conn = sqlite3.connect('data/fongmi.db')
    c = conn.cursor()
    c.execute("SELECT key, api FROM site WHERE type=1")
    rows = c.fetchall()
    conn.close()

    vod_sites = []
    for key, api in rows:
        if not api:
            continue
        base = api.rstrip("/")
        if "api.php/provide/vod" not in base:
            base = base + "/api.php/provide/vod"
        try:
            import urllib.parse
            url = f"{base}?{urllib.parse.urlencode({'ac': 'list', 'pg': '1'})}"
            text = http_get_sync(url, timeout=10, headers={"User-Agent": "okhttp/3.10.0"}).strip()
            if len(text) < 10:
                continue
            data = json.loads(text)
            items = data.get("list", [])
            real = [i for i in items if "_" not in str(i.get("vod_id", ""))]
            if len(real) >= 3:
                vod_sites.append({"key": key, "name": key, "api": api})
        except Exception:
            continue

    _VOD_SITES_CACHE = vod_sites
    logger.info(f"VOD sites: {len(vod_sites)} - {[s['key'] for s in vod_sites]}")
    return vod_sites
