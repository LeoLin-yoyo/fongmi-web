"""Spider Engine - dispatches to correct runtime based on site type"""
import hashlib
import threading
import urllib.parse
import urllib.request
from collections import OrderedDict
from loguru import logger

from spider.net import ensure_http_url

try:
    from model.bean import Site
except ImportError:
    from spider.models import Site


class _LRUCache:
    def __init__(self, maxsize=50):
        self._store = OrderedDict()
        self._max = maxsize

    def get(self, key):
        if key in self._store:
            self._store.move_to_end(key)
            return self._store[key]
        return None

    def put(self, key, value):
        if key in self._store:
            self._store.move_to_end(key)
        else:
            if len(self._store) >= self._max:
                self._store.popitem(last=False)
        self._store[key] = value

    def clear(self):
        self._store.clear()


def _download_url(url: str, timeout: int = 3) -> str:
    """下载远程 URL 内容（短超时，避免卡死）"""
    # URL 编码非 ASCII 字符
    parsed = urllib.parse.urlparse(url)
    path = urllib.parse.quote(parsed.path, safe='/:@!$&\'()*+,;=-._~')
    if path != parsed.path:
        url = urllib.parse.urlunparse(parsed._replace(path=path))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _is_csp_class(api: str) -> bool:
    """判断是否为 csp_XXX 类名"""
    return api.startswith("csp_") or api.startswith("assets://")


def _is_remote_url(api: str) -> bool:
    return api.startswith(("http://", "https://"))


def _is_py_file(api: str) -> bool:
    return api.endswith(".py")


def _get_builtin_spider(api: str, ext: str):
    """从内置 JS 注册表获取 csp_XXX 爬虫"""
    import os
    js_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "builtin.js")
    if not os.path.exists(js_path):
        return None
    try:
        with open(js_path, "r", encoding="utf-8") as f:
            js_code = f.read()
        from spider.js_runtime import SpiderJSRuntime
        rt = SpiderJSRuntime()
        rt.load_spider(js_code)
        class_name = api if api.startswith("csp_") else "csp_" + api
        try:
            fn = rt.ctx.get("loadCspSpider")
            if fn:
                # quickjs 非线程安全，直接执行也必须持全局锁
                from spider.js_runtime import SpiderJSRuntime as _SJR
                with _SJR._QJS_LOCK:
                    ok = fn(class_name, ext)
                if ok:
                    return rt
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Builtin spider failed for {api}: {e}")
    return None


class _SpiderInstance:
    def __init__(self, spider_type, api, ext, jar):
        self.spider_type = spider_type
        self.api = api
        self.ext = ext
        self.jar = jar
        self._runtime = None
        self._lock = threading.Lock()

    def _ensure_runtime(self):
        if self._runtime is not None:
            return
        with self._lock:
            if self._runtime is not None:
                return
            if self.spider_type == 1:
                from spider.http_spider import HttpSpider
                self._runtime = HttpSpider(self.api, self.ext or "")
            elif self.spider_type == 3:
                # 尝试内置 csp_XXX 爬虫
                if _is_csp_class(self.api):
                    rt = _get_builtin_spider(self.api, self.ext or "")
                    if rt:
                        self._runtime = rt
                    return

                if _is_py_file(self.api):
                    return

                js_code = self._read_api()
                if not js_code or js_code == self.api:
                    return

                if self.api.endswith(".js") and _is_remote_url(self.api):
                    import shutil
                    if shutil.which("node"):
                        from spider.node_runtime import NodeSpider, ensure_engine
                        if ensure_engine():
                            rt = NodeSpider(self.api, self.api, self.ext or "")
                            rt.load()
                            self._runtime = rt
                            return

                from spider.js_runtime import SpiderJSRuntime
                rt = SpiderJSRuntime()
                try:
                    rt.load_spider(js_code)
                    self._runtime = rt
                except Exception as e:
                    logger.error(f"Load spider failed for {self.api}: {e}")
            else:
                logger.warning(f"Unsupported type: {self.spider_type}")

    def _read_api(self):
        import os
        if os.path.isfile(self.api):
            with open(self.api, "r", encoding="utf-8") as f:
                return f.read()
        if _is_remote_url(self.api):
            if _is_py_file(self.api):
                return ""
            try:
                return _download_url(self.api, timeout=3)
            except Exception as e:
                logger.error(f"Download {self.api[:60]} failed: {e}")
                return ""
        return self.api

    def call(self, method, *args):
        self._ensure_runtime()
        if self._runtime is None:
            return {}
        return self._runtime.call(method, *args)


class SpiderEngine:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._cache = _LRUCache()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _key(self, site):
        return hashlib.md5(f"{site.key}|{site.api}|{site.ext}|{site.jar}".encode()).hexdigest()

    def get_spider(self, site):
        k = self._key(site)
        spider = self._cache.get(k)
        if spider:
            return spider
        spider = _SpiderInstance(site.type, site.api, site.ext, site.jar)
        self._cache.put(k, spider)
        return spider


engine = SpiderEngine.get_instance()


async def home_content(site, filter=True):
    spider = engine.get_spider(site)
    import asyncio
    return await asyncio.to_thread(spider.call, "homeContent", filter)


async def category_content(site, tid, pg, filter, extend):
    spider = engine.get_spider(site)
    import asyncio
    return await asyncio.to_thread(spider.call, "categoryContent", tid, pg, filter, extend)


async def detail_content(site, ids):
    spider = engine.get_spider(site)
    import asyncio
    return await asyncio.to_thread(spider.call, "detailContent", ids)


async def search_content(site, key, quick=False, pg=""):
    spider = engine.get_spider(site)
    import asyncio
    return await asyncio.to_thread(spider.call, "searchContent", key)


async def player_content(site, flag, id, vip_flags=None, parses=None):
    spider = engine.get_spider(site)
    import asyncio
    result = await asyncio.to_thread(spider.call, "playerContent", flag, id)
    if parses and result.get("parse") == 1:
        from spider.parser import ParserEngine
        pe = ParserEngine(parses)
        resolved = await pe.resolve(result.get("url", ""), flag)
        if resolved:
            result.update(resolved)
    return result


async def live_content(site, url=""):
    spider = engine.get_spider(site)
    import asyncio
    return await asyncio.to_thread(spider.call, "liveContent", url)