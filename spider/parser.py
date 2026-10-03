"""Parser Engine - resolves play URLs using configured parsers"""
import json
import re
import urllib.parse
from loguru import logger

from spider.http_sync import http_get_sync


class ParserEngine:
    def __init__(self, parses: list[dict]):
        self.parses = parses

    async def resolve(self, url: str, flag: str = "") -> dict:
        for parse in self.parses:
            try:
                result = await self._try_parse(parse, url, flag)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"Parse failed: {e}")
        return {"parse": 0, "url": url, "flag": flag}

    async def _try_parse(self, parse: dict, url: str, flag: str) -> dict | None:
        parse_type = parse.get("type", 0)
        parse_url = parse.get("url", "")

        if parse_type == 0:
            import asyncio
            resolved = await asyncio.to_thread(self._jsonp_parse, parse_url, url, flag)
            if resolved:
                return {"parse": 0, "url": resolved, "flag": flag}
        elif parse_type == 1:
            resolved = self._direct_parse(parse_url, url)
            if resolved:
                return {"parse": 0, "url": resolved, "flag": flag}

        return None

    def _jsonp_parse(self, parse_url: str, url: str, flag: str) -> str | None:
        filled = parse_url.replace("{url}", urllib.parse.quote(url, safe=""))
        filled = filled.replace("{flag}", flag)

        try:
            text = http_get_sync(filled, timeout=15, headers={"User-Agent": "okhttp/3.10.0"}).strip()
            match = re.search(r'\{[^}]+\}', text)
            if match:
                data = json.loads(match.group())
                return data.get("url", "") or data.get("playUrl", "")
            data = json.loads(text)
            return data.get("url", "") or data.get("playUrl", "")
        except Exception as e:
            logger.debug(f"JSONP parse error: {e}")
            return None

    def _direct_parse(self, parse_url: str, url: str) -> str:
        return parse_url.replace("{url}", url)
