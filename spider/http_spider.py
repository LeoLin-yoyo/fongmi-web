"""HTTP Spider for type=1 JSON API sites (standard PHP VOD API)"""
import json
import urllib.parse
from loguru import logger

from spider.http_sync import http_get_sync


class HttpSpider:
    def __init__(self, api_url: str, ext: str = ""):
        self.api_url = api_url.rstrip("/").rstrip("?")
        self.ext = ext
        self._headers = {"User-Agent": "okhttp/3.10.0"}

    def call(self, method: str, *args):
        """Dispatch to the right method, returns sync result"""
        fn = getattr(self, method, None)
        if fn:
            return fn(*args)
        return {}

    def _build_url(self, params: dict = None) -> str:
        base = self.api_url.split("?")[0].rstrip("/") if "?" in self.api_url else self.api_url.rstrip("/")
        # 仅裸域名补默认路径；配置已带 API 路径（如 api.php/seaxml/vod）时原样使用，
        # 否则会拼出 .../seaxml/vod/api.php/provide/vod/ 这类失效地址
        if not urllib.parse.urlparse(base).path.strip("/"):
            base = base + "/api.php/provide/vod/"
        query = ""
        if params:
            clean = {k: str(v) for k, v in params.items() if v is not None}
            query = urllib.parse.urlencode(clean)
        sep = "?" if "?" not in base.split("/")[-1] else "&"
        return f"{base}{sep}{query}" if query else base

    def _fetch(self, url: str) -> str:
        try:
            return http_get_sync(url, timeout=15, headers=self._headers)
        except Exception as e:
            logger.debug(f"Fetch failed {url}: {e}")
            return ""

    def homeContent(self, filter=True):
        text = self._fetch(self._build_url())
        if not text:
            return {}
        result = self._parse_list(text)
        if result.get("list"):
            has_pic = any(item.get("vod_pic") for item in result["list"])
            if not has_pic:
                ids = [str(item["vod_id"]) for item in result["list"] if item.get("vod_id")]
                if ids:
                    self._fetch_pics(result, ids)
        return result

    def _fetch_pics(self, result: dict, ids: list):
        """Two-step picture fetch like original Fongmi"""
        try:
            text = self._fetch(self._build_url({"ac": "detail", "ids": ",".join(ids)}))
            if not text:
                return
            detail = self._parse_list(text)
            pic_map = {}
            for item in detail.get("list", []):
                vid = str(item.get("vod_id", ""))
                pic = item.get("vod_pic", "")
                if vid and pic:
                    pic_map[vid] = pic
            for item in result["list"]:
                vid = str(item.get("vod_id", ""))
                if not item.get("vod_pic") and vid in pic_map:
                    item["vod_pic"] = pic_map[vid]
        except Exception as e:
            logger.debug(f"Fetch pics failed: {e}")

    def categoryContent(self, tid, pg, filter, extend=None):
        params = {"ac": "videolist", "t": str(tid), "pg": str(pg)}
        if extend:
            for k, v in extend.items():
                params[k] = str(v) if v is not None else ""
        text = self._fetch(self._build_url(params))
        if not text:
            return {}
        result = self._parse_list(text)
        if result.get("list"):
            has_pic = any(item.get("vod_pic") for item in result["list"])
            if not has_pic:
                ids = [str(item["vod_id"]) for item in result["list"] if item.get("vod_id")]
                if ids:
                    self._fetch_pics(result, ids)
        return result

    def detailContent(self, ids):
        params = {"ac": "detail", "ids": ",".join(str(i) for i in ids)}
        text = self._fetch(self._build_url(params))
        if not text:
            return {}
        return self._parse_list(text)

    def searchContent(self, key, quick=False, pg=""):
        params = {"wd": key}
        if pg and pg != "1":
            params["pg"] = str(pg)
        text = self._fetch(self._build_url(params))
        if not text:
            return {}
        result = self._parse_list(text)
        if result.get("list"):
            has_pic = any(item.get("vod_pic") for item in result["list"])
            if not has_pic:
                ids = [str(item["vod_id"]) for item in result["list"] if item.get("vod_id")]
                if ids:
                    self._fetch_pics(result, ids)
        return result

    def playerContent(self, flag, id, vip_flags=None):
        url = id
        if "m3u8" in url.lower() or ".mp4" in url.lower() or ".flv" in url.lower():
            return {"parse": 0, "url": url, "flag": flag}
        return {"parse": 1, "url": url, "flag": flag}

    def liveContent(self, url=""):
        return ""

    def _parse_list(self, text):
        try:
            data = json.loads(text)
            result = {}
            if "class" in data:
                result["class"] = data["class"]
            if "list" in data:
                vod_list = data["list"]
                formatted = []
                for v in vod_list:
                    if isinstance(v, dict):
                        item = {
                            "vod_id": str(v.get("vod_id", v.get("id", ""))),
                            "vod_name": v.get("vod_name", v.get("name", "")),
                            "vod_pic": v.get("vod_pic", v.get("pic", "")),
                            "vod_remarks": v.get("vod_remarks", v.get("remarks", "")),
                            "vod_year": v.get("vod_year", ""),
                            "vod_area": v.get("vod_area", ""),
                            "vod_actor": v.get("vod_actor", ""),
                            "vod_director": v.get("vod_director", ""),
                            "vod_content": v.get("vod_content", ""),
                            "vod_play_from": v.get("vod_play_from", ""),
                            "vod_play_url": v.get("vod_play_url", ""),
                            "vod_tag": v.get("vod_tag", ""),
                            "type_name": v.get("type_name", ""),
                        }
                        formatted.append(item)
                result["list"] = formatted
            if "page" in data:
                result["page"] = data["page"]
            if "pagecount" in data:
                result["pagecount"] = data["pagecount"]
            if "total" in data:
                result["total"] = data["total"]
            if "filters" in data:
                result["filters"] = data["filters"]
            return result
        except json.JSONDecodeError:
            return {"error": "JSON parse error", "raw": text[:200]}
        except Exception as e:
            return {"error": str(e)}
