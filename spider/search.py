"""Aggregate search - all sites in parallel, merged results

支持两类站点：
- type==1: CMS 站点，直接 HTTP 搜索接口
- type==3 / csp_ 爬虫站点：走 spider engine（JS/builtin 运行时）
拼音容错：纯 ASCII 关键词（如 shenxia）通过本地片名拼音索引回搜（T3-1）。
"""
import json
import asyncio
import ssl
import urllib.request
from loguru import logger
from sqlalchemy import select

from spider.net import ensure_http_url
from spider.pinyin_index import title_index, _is_ascii_keyword


_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

_SITE_TIMEOUT = 10
_PINYIN_SITE_TIMEOUT = 8
_MAX_PINYIN_RESEARCH = 3


def _search_timeout() -> int:
    return 20


async def search_all(keyword: str) -> list:
    """Search all VOD sites in parallel, return merged items with pictures"""
    result = await search_aggregated(keyword)
    return result["merged"]


def _normalize_spider_result(raw, site_key: str, site_name: str) -> list:
    """spider.searchContent 返回 dict{'list': [...]} / list / None，统一为 item 列表"""
    items = []
    if isinstance(raw, dict):
        items = raw.get("list") or []
    elif isinstance(raw, list):
        items = raw
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("vod_name", "") or "")
        if not name:
            continue
        if name.startswith("✈") or "关注" in name:
            continue
        item["_site_key"] = site_key
        item["_site_name"] = site_name
        result.append(item)
    return result


async def _search_spider_site(site_key, site_name, api_url, site_ext, keyword):
    """type==3 / csp_ 站点搜索，走 spider engine"""
    from model.bean import Site
    from spider.engine import search_content

    site = Site(key=site_key, name=site_name, type=3, api=api_url,
                ext=site_ext or "", jar="", searchable=1, quickSearch=1, filterable=1)
    raw = await asyncio.wait_for(search_content(site, keyword), timeout=_SITE_TIMEOUT)
    return _normalize_spider_result(raw, site_key, site_name)


async def search_aggregated(keyword: str) -> dict:
    """Search all VOD sites in parallel, return {merged, per_site: {site_key: {name, results}}}"""
    from model.database import async_session, Site as SiteModel, Config as ConfigModel

    async with async_session() as session:
        enabled_configs = await session.execute(
            select(ConfigModel).where(ConfigModel.enabled == 1)
        )
        enabled_ids = [c.id for c in enabled_configs.scalars().all()]
        if not enabled_ids:
            return {"merged": [], "per_site": {}}

        result = await session.execute(
            select(SiteModel).where(SiteModel.searchable == 1, SiteModel.config_id.in_(enabled_ids))
        )
        site_rows = result.scalars().all()

    site_info = {s.key: {"name": s.name, "api": s.api, "type": s.type, "ext": s.ext} for s in site_rows}
    coros = [_search_one_row(s.key, s.name, s.api, s.type, s.ext, keyword) for s in site_rows]
    try:
        results = await asyncio.wait_for(asyncio.gather(*coros, return_exceptions=True), timeout=_search_timeout())
    except asyncio.TimeoutError:
        logger.warning("Search timed out")
        results = []

    merged = []
    per_site = {}
    for i, r in enumerate(results):
        site_key = site_rows[i].key if i < len(site_rows) else None
        if isinstance(r, list):
            merged.extend(r)
            if site_key:
                per_site[site_key] = {"name": site_info[site_key]["name"], "results": r}
        elif isinstance(r, Exception):
            logger.debug(f"Search {site_key} failed: {r}")
            if site_key:
                per_site[site_key] = {"name": site_info[site_key]["name"], "results": []}

    # 登记片名到拼音索引，供后续拼音关键词回搜
    try:
        title_index.add_titles(
            [item.get("vod_name", "") for item in merged if item.get("vod_name")],
            site_key="",
        )
    except Exception as e:
        logger.debug(f"title index add failed: {e}")

    # 拼音容错：纯 ASCII 关键词且站点直搜结果不足时，用索引命中的中文片名回搜
    if _is_ascii_keyword(keyword):
        merged, per_site = await _expand_with_pinyin(keyword, merged, per_site, site_info)

    seen = set()
    unique = []
    for item in merged:
        name = item.get("vod_name", "")
        site_key = item.get("_site_key", "")
        key = f"{site_key}:{name}"
        if name and key not in seen:
            seen.add(key)
            unique.append(item)

    return {"merged": unique, "per_site": per_site}


async def _expand_with_pinyin(keyword: str, merged: list, per_site: dict, site_info: dict) -> tuple:
    """拼音关键词 → 索引命中中文片名 → 回搜站点，补充结果"""
    try:
        matched_titles = title_index.find_by_keyword(keyword, limit=_MAX_PINYIN_RESEARCH)
    except Exception as e:
        logger.debug(f"pinyin lookup failed: {e}")
        return merged, per_site
    if not matched_titles:
        return merged, per_site

    known_names = {item.get("vod_name", "") for item in merged}
    todo_titles = [t for t in matched_titles if t not in known_names]
    if not todo_titles:
        return merged, per_site

    for title in todo_titles[:_MAX_PINYIN_RESEARCH]:
        coros = [_search_one_row(s_key, s["name"], s["api"], s["type"], s["ext"], title,
                                 timeout=_PINYIN_SITE_TIMEOUT)
                 for s_key, s in site_info.items()]
        try:
            results = await asyncio.wait_for(asyncio.gather(*coros, return_exceptions=True),
                                             timeout=_search_timeout())
        except asyncio.TimeoutError:
            continue
        for i, r in enumerate(results):
            if not isinstance(r, list) or not r:
                continue
            s_key = list(site_info.keys())[i]
            for item in r:
                item["_site_key"] = s_key
                item["_site_name"] = site_info[s_key]["name"]
                item["_pinyin_match"] = keyword
            merged.extend(r)
            if s_key in per_site:
                per_site[s_key]["results"].extend(r)
            else:
                per_site[s_key] = {"name": site_info[s_key]["name"], "results": r}
    return merged, per_site


async def _search_one_row(site_key, site_name, api_url, site_type, site_ext, keyword,
                          timeout: int = _SITE_TIMEOUT):
    """Search a single site by type"""
    if not api_url:
        return []

    if api_url.startswith("assets://"):
        return []

    if api_url.endswith(".py"):
        return []

    if site_type == 3 or api_url.startswith("csp_"):
        try:
            return await asyncio.wait_for(
                _search_spider_site(site_key, site_name, api_url, site_ext, keyword),
                timeout=timeout)
        except asyncio.TimeoutError:
            logger.debug(f"Spider search {site_key} timed out")
            return []
    elif site_type == 1:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_search, site_key, site_name, api_url, keyword)
    else:
        return []


def _sync_search(site_key, site_name, api_url, keyword):
    """Synchronous search using urllib"""
    base = api_url.rstrip("/")
    import urllib.parse
    params = urllib.parse.urlencode({"wd": keyword, "pg": "1"})
    sep = "&" if "?" in base else "?"
    url = f"{base}{sep}{params}"

    req = urllib.request.Request(url, headers={"User-Agent": "okhttp/3.10.0"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=_SSL_CTX) as resp:
            text = resp.read().decode("utf-8", errors="replace").strip()
            if not text or "暂不支持" in text or len(text) < 10:
                return []
            data = json.loads(text)
            items = data.get("list", [])

            filtered = []
            for item in items:
                vid = str(item.get("vod_id", ""))
                name = item.get("vod_name", "")
                parts = vid.split("_")
                if len(parts) == 3 and all(p.isdigit() for p in parts):
                    continue
                if name.startswith("✈") or "关注" in name:
                    continue
                item["_site_key"] = site_key
                item["_site_name"] = site_name
                filtered.append(item)

            if filtered:
                has_pic = any(i.get("vod_pic") for i in filtered)
                if not has_pic:
                    _fetch_pics_sync(base, filtered)

            return filtered
    except Exception as e:
        logger.debug(f"Search {site_key} error: {e}")
        return []


def _fetch_pics_sync(base, items):
    """Fetch pictures for items"""
    try:
        ids = [str(i["vod_id"]) for i in items if i.get("vod_id")]
        if not ids:
            return
        clean_base = base.split("?")[0].rstrip("/") if "?" in base else base.rstrip("/")
        # 与 http_spider._build_url 同规则：仅裸域名补默认路径
        import urllib.parse
        if not urllib.parse.urlparse(clean_base).path.strip("/"):
            clean_base = clean_base + "/api.php/provide/vod/"
        params = urllib.parse.urlencode({"ac": "detail", "ids": ",".join(ids)})
        url = f"{clean_base}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "okhttp/3.10.0"})
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            text = resp.read().decode("utf-8", errors="replace").strip()
            detail = json.loads(text)
            pic_map = {}
            for d in detail.get("list", []):
                vid = str(d.get("vod_id", ""))
                pic = d.get("vod_pic", "")
                if vid and pic:
                    pic_map[vid] = pic
            for item in items:
                vid = str(item.get("vod_id", ""))
                if not item.get("vod_pic") and vid in pic_map:
                    item["vod_pic"] = pic_map[vid]
    except Exception as e:
        logger.debug(f"Fetch pics error: {e}")
