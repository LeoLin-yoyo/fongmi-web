"""QuickJS 引擎，负责加载和执行 JS 格式的爬虫"""
import hashlib
import json
import re
import signal
import threading
from urllib.parse import urlencode, urljoin

import quickjs
from loguru import logger

from spider.net import NetClient


class _TimeoutError(Exception):
    pass


class _HTMLNode:
    """轻量级 HTML 解析节点，支持 CSS 选择器"""

    def __init__(self, tag=None, attrs=None, text=""):
        self.tag = tag or ""
        self.attrs = attrs or {}
        self.text = text
        self.children: list["_HTMLNode"] = []
        self.parent: "_HTMLNode | None" = None

    def find(self, selector: str) -> list["_HTMLNode"]:
        """支持 tag.class > tag, tag[attr=value], tag:contains(...) 等"""
        results = []
        self._match_recursive(self, selector.strip(), results)
        return results

    @staticmethod
    def _match_recursive(node: "_HTMLNode", selector: str, results: list):
        parts = _HTMLNode._parse_selector(selector)
        if node._matches(parts[0]):
            if len(parts) == 1:
                results.append(node)
            else:
                for child in node.children:
                    _HTMLNode._match_descendant(child, parts[1:], results)
        for child in node.children:
            _HTMLNode._match_recursive(child, selector, results)

    @staticmethod
    def _match_descendant(node: "_HTMLNode", parts: list[dict], results: list):
        if node._matches(parts[0]):
            if len(parts) == 1:
                results.append(node)
            else:
                for child in node.children:
                    _HTMLNode._match_descendant(child, parts[1:], results)
        for child in node.children:
            _HTMLNode._match_descendant(child, parts, results)

    def _matches(self, rule: dict) -> bool:
        if not rule:
            return False
        if rule.get("tag") and self.tag != rule["tag"]:
            return False
        if rule.get("id") and self.attrs.get("id") != rule["id"]:
            return False
        for cls in rule.get("classes", []):
            cls_attr = self.attrs.get("class", "")
            if cls not in cls_attr.split():
                return False
        for attr, val in rule.get("attrs", {}).items():
            if self.attrs.get(attr) != val:
                return False
        return True

    @staticmethod
    def _parse_selector(sel: str) -> list[dict]:
        parts = []
        for token in re.split(r"\s*>\s*|\s+", sel.strip()):
            if not token:
                continue
            rule = {}
            tag_match = re.match(r"^([\w\-\*]+)?", token)
            if tag_match and tag_match.group(1):
                rule["tag"] = tag_match.group(1)
            id_match = re.search(r"#([\w\-]+)", token)
            if id_match:
                rule["id"] = id_match.group(1)
            for cls_match in re.finditer(r"\.([\w\-]+)", token):
                rule.setdefault("classes", []).append(cls_match.group(1))
            for attr_match in re.finditer(r'\[([\w\-]+)=["\']?([^"\']+)["\']?\]', token):
                rule.setdefault("attrs", {})[attr_match.group(1)] = attr_match.group(2)
            parts.append(rule)
        return parts if parts else [{}]

    def get_text(self) -> str:
        texts = []
        if self.text:
            texts.append(self.text.strip())
        for child in self.children:
            texts.append(child.get_text())
        return " ".join(t for t in texts if t)

    def __repr__(self):
        return f"<{self.tag} {self.attrs}>{self.get_text()[:50]}</{self.tag}>"


def _parse_html(html_str: str) -> _HTMLNode:
    """简易 HTML parser -> DOM tree"""
    root = _HTMLNode(tag="root")
    stack = [root]
    tag_re = re.compile(r"<(/?)([\w\-]+)((?:\s+[\w\-]+(?:=['\"][^'\"]*['\"])?)*)\s*/?>([^<]*)", re.S)
    close_re = re.compile(r"< /?[\w\-]+[^>]*>", re.S)

    pos = 0
    for m in tag_re.finditer(html_str):
        full = m.group(0)
        is_close = m.group(1) == "/"
        tag_name = m.group(2).lower()
        attrs_str = m.group(3) or ""
        text_after = m.group(4) or ""

        if is_close:
            for i in range(len(stack) - 1, 0, -1):
                if stack[i].tag == tag_name:
                    stack = stack[:i]
                    break
            continue

        attrs = {}
        for a in re.finditer(r"([\w\-]+)=['\"]([^'\"]*)['\"]", attrs_str):
            attrs[a.group(1).lower()] = a.group(2)

        node = _HTMLNode(tag=tag_name, attrs=attrs)
        stack[-1].children.append(node)
        node.parent = stack[-1]

        if text_after and text_after.strip():
            text_node = _HTMLNode(text=text_after)
            node.children.append(text_node)
            text_node.parent = node

        void_tags = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr"}
        if tag_name not in void_tags and not full.endswith("/>"):
            stack.append(node)

    return root


class _SyncFetch:
    """Synchronous bridge for JS fetch() -> httpx"""

    def __init__(self, net: NetClient):
        self._net = net

    def __call__(self, url: str, options: dict | None = None) -> dict:
        import asyncio
        options = options or {}
        headers = options.get("headers", {})
        method = options.get("method", "GET").upper()

        async def _do():
            try:
                if method == "GET":
                    text = await self._net.get(url, headers=headers if headers else None)
                else:
                    data = options.get("body", "")
                    text = await self._net.post(url, data=data, headers=headers if headers else None)
                return {"ok": True, "status": 200, "text": text}
            except Exception as e:
                logger.warning(f"Fetch failed: {url} -> {e}")
                return {"ok": False, "status": 500, "text": str(e)}

        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _do())
                return future.result(timeout=30)
        except RuntimeError:
            return asyncio.run(_do())


class SpiderJSRuntime:
    # quickjs 绑定存在进程级共享 C 状态（module.c 线程断言），任何两个 Context 的
    # eval/call 并发执行都会直接 abort 整个进程 —— 全局串行化是硬性要求
    _QJS_LOCK = threading.Lock()

    def __init__(self):
        # quickjs.Context() 创建与全局注入涉及共享 C 状态，必须持全局锁（进程级串行是硬性要求）
        with SpiderJSRuntime._QJS_LOCK:
            self.ctx = quickjs.Context()
            self._logs: list[str] = []
            self._net = NetClient()
            self._fetch = _SyncFetch(self._net)
            self._html_store: dict[int, _HTMLNode] = {}
            self._html_counter = 0
            self._inject_globals()

    def _inject_globals(self):
        logs = self._logs
        fetch = self._fetch
        parse_html_fn = _parse_html
        html_store = self._html_store
        html_counter = [0]

        def _store_html(node: _HTMLNode) -> int:
            html_counter[0] += 1
            handle = html_counter[0]
            html_store[handle] = node
            return handle

        def js_print(*args):
            line = " ".join(str(a) for a in args)
            logs.append(line)
            logger.debug(f"[JS] {line}")

        def js_fetch(url, options=None):
            result = fetch(url, options)
            return json.dumps(result, ensure_ascii=False)

        def js_build_url(url, obj):
            if "?" in url:
                url += "&"
            else:
                url += "?"
            return url + urlencode(obj)

        def js_html(html_str):
            node = parse_html_fn(html_str)
            return _store_html(node)

        def js_find(handle, selector):
            node = html_store.get(handle)
            if node is None:
                return "[]"
            results = node.find(selector)
            return json.dumps([n.get_text() for n in results], ensure_ascii=False)

        def js_find_attr(handle, selector, attr):
            node = html_store.get(handle)
            if node is None:
                return "[]"
            results = node.find(selector)
            return json.dumps([n.attrs.get(attr, "") for n in results], ensure_ascii=False)

        def js_get_text(handle):
            node = html_store.get(handle)
            if node is None:
                return ""
            return node.get_text()

        def js_pdfh(html_str, selector):
            node = parse_html_fn(html_str)
            results = node.find(selector)
            return json.dumps([n.get_text() for n in results], ensure_ascii=False)

        def js_pd(html_str, selector, base_url=""):
            node = parse_html_fn(html_str)
            results = node.find(selector)
            texts = []
            for n in results:
                t = n.get_text()
                href = n.attrs.get("href", "")
                if not _url_re.match(href) and base_url:
                    href = urljoin(base_url, href)
                texts.append(f"{href}$${t}" if href else t)
            return json.dumps(texts, ensure_ascii=False)

        _url_re = re.compile(r"^https?://")

        def js_atob(s):
            import base64
            return base64.b64decode(s).decode("utf-8", errors="replace")

        def js_md5(s):
            return hashlib.md5(s.encode()).hexdigest()

        def js_to_string(obj):
            return str(obj)

        self.ctx.add_callable("print", js_print)
        self.ctx.add_callable("fetch", js_fetch)
        self.ctx.add_callable("buildUrl", js_build_url)
        self.ctx.add_callable("html", js_html)
        self.ctx.add_callable("find", js_find)
        self.ctx.add_callable("findAttr", js_find_attr)
        self.ctx.add_callable("getText", js_get_text)
        self.ctx.add_callable("pdfh", js_pdfh)
        self.ctx.add_callable("pd", js_pd)
        self.ctx.add_callable("atob", js_atob)
        self.ctx.add_callable("md5", js_md5)
        self.ctx.add_callable("toString", js_to_string)

        ctx_eval = """
        var console = {
            log: function() { print.apply(null, arguments); },
            error: function() { print.apply(null, arguments); },
            warn: function() { print.apply(null, arguments); }
        };
        var globalThis = {};
        var window = globalThis;
        var self = globalThis;
        """
        self.ctx.eval(ctx_eval)

    def load_spider(self, js_code: str):
        try:
            with SpiderJSRuntime._QJS_LOCK:
                self.ctx.eval(js_code)
            logger.debug("JS spider loaded successfully")
        except quickjs.JSException as e:
            logger.error(f"Load JS spider failed: {e}")
            raise

    def _to_js_arg(self, arg):
        if isinstance(arg, (dict, list)):
            return self.ctx.parse_json(json.dumps(arg, ensure_ascii=False))
        return arg

    def call(self, method: str, *args):
        timeout = 10

        result = [None]
        error = [None]
        done = threading.Event()

        def _run():
            try:
                # 全局锁内执行 quickjs；拿不到锁说明有别的 JS 调用在跑，直接返回 busy
                if not SpiderJSRuntime._QJS_LOCK.acquire(timeout=timeout):
                    result[0] = {"error": "busy"}
                    return
                try:
                    fn = self.ctx.get(method)
                    if fn is None:
                        result[0] = {}
                        return
                    js_args = [self._to_js_arg(a) for a in args]
                    raw = fn(*js_args)
                    if raw is None:
                        result[0] = {}
                    elif isinstance(raw, (int, float, bool)):
                        result[0] = raw
                    elif isinstance(raw, str):
                        if raw.strip().startswith(("{", "[")):
                            try:
                                result[0] = json.loads(raw)
                            except json.JSONDecodeError:
                                result[0] = raw
                        else:
                            result[0] = raw
                    else:
                        s = str(raw)
                        if s.startswith(("{", "[")):
                            try:
                                result[0] = json.loads(s)
                            except json.JSONDecodeError:
                                result[0] = s
                        else:
                            result[0] = s
                finally:
                    SpiderJSRuntime._QJS_LOCK.release()
            except quickjs.JSException as e:
                error[0] = e
            except Exception as e:
                error[0] = e
            finally:
                done.set()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        if not done.wait(timeout):
            logger.error(f"JS call {method} timed out after {timeout}s")
            return {"error": "timeout"}
        if error[0]:
            logger.error(f"JS call {method} error: {error[0]}")
            return {"error": str(error[0])}
        if isinstance(result[0], str):
            try:
                return json.loads(result[0])
            except json.JSONDecodeError:
                return result[0]
        return result[0] if result[0] is not None else {}

    def destroy(self):
        try:
            self.ctx.eval("__JS_SPIDER__ && typeof __JS_SPIDER__.destroy === 'function' && __JS_SPIDER__.destroy()")
        except Exception:
            pass
        self._html_store.clear()
