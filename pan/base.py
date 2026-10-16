"""网盘平台客户端基类：httpx 封装 + Set-Cookie 会话回填 + 统一响应解析。

YunX 硬规则移植：
- 所有请求跟随代理（spider.proxy_config，TG/网盘同一套代理口径）
- 响应 Set-Cookie 里的 __puus/__pus/__pugs 合并回账号 Cookie 并回调 sink（会话保鲜）
- 取链/下载必须带完整请求头，直链 302 视为 Cookie 失效
- 服务端返回非 JSON 时带上 HTTP 状态码，便于分辨「未登录被拒」与「分享失效」
"""
import json
from urllib.parse import quote

import httpx
from loguru import logger

from spider.proxy_config import get_proxy_with_detect

from .cookies import merge_from_set_cookies
from .models import PanError


class PanClient:
    platform = ""
    label = ""
    # 登录必需的 Cookie 关键字段：全部存在才算已登录（各平台覆写）
    REQUIRED_COOKIES: tuple = ()
    # 支持游客（不登录）取链播放
    GUEST_SUPPORTED = False

    def __init__(self, cookie: str = "", cookie_sink=None):
        self.cookie = (cookie or "").strip()
        self._cookie_sink = cookie_sink
        self._proxy_url = ""
        self._client = self._build_client()

    def _build_client(self) -> httpx.AsyncClient:
        kwargs = dict(
            follow_redirects=False, verify=False,
            timeout=httpx.Timeout(30.0, read=60.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        )
        proxy = get_proxy_with_detect()
        if proxy:
            kwargs["proxy"] = proxy
        self._proxy_url = proxy or ""
        return httpx.AsyncClient(**kwargs)

    def _ensure_proxy(self):
        # httpx 的代理在 client 级绑定；设置页改过代理则重建 client
        want = get_proxy_with_detect() or ""
        if want != self._proxy_url:
            old = self._client
            self._client = self._build_client()
            import asyncio

            async def _close():
                try:
                    await old.aclose()
                except Exception:
                    pass
            try:
                asyncio.get_running_loop().create_task(_close())
            except RuntimeError:
                pass

    async def aclose(self):
        try:
            await self._client.aclose()
        except Exception:
            pass

    @classmethod
    def is_valid_cookie(cls, cookie: str) -> bool:
        cookie = cookie or ""
        return bool(cls.REQUIRED_COOKIES) and all(f"{k}=" in cookie for k in cls.REQUIRED_COOKIES)

    # ---------- HTTP ----------
    def _headers(self, extra: dict | None = None, cookie: str | None = None) -> dict:
        h = {"User-Agent": self.api_user_agent()}
        ck = cookie if cookie is not None else self.cookie
        if ck:
            h["Cookie"] = ck
        h.update(extra or {})
        return h

    def api_user_agent(self) -> str:
        return "Mozilla/5.0"

    def _merge_cookies(self, resp: httpx.Response):
        set_cookies = [v for k, v in resp.headers.items() if k.lower() == "set-cookie"]
        if not set_cookies or not self.cookie:
            return
        merged = merge_from_set_cookies(self.cookie, set_cookies)
        if merged != self.cookie:
            self.cookie = merged
            if self._cookie_sink:
                try:
                    self._cookie_sink(self.platform, merged)
                except Exception as e:
                    logger.debug(f"cookie sink 失败: {e}")

    async def get_json(self, url: str, headers: dict | None = None,
                       cookie: str | None = None) -> dict:
        h = self._headers(headers, cookie)
        self._ensure_proxy()
        try:
            resp = await self._client.get(url, headers=h)
        except httpx.HTTPError as e:
            raise PanError(f"网络请求失败: {str(e)[:120]}") from e
        self._merge_cookies(resp)
        return self._parse_json(resp)

    async def post_json(self, url: str, body: dict, headers: dict | None = None,
                        cookie: str | None = None) -> dict:
        h = {"Content-Type": "application/json", **self._headers(headers, cookie)}
        self._ensure_proxy()
        try:
            resp = await self._client.post(url, json=body, headers=h)
        except httpx.HTTPError as e:
            raise PanError(f"网络请求失败: {str(e)[:120]}") from e
        self._merge_cookies(resp)
        return self._parse_json(resp)

    def _parse_json(self, resp: httpx.Response) -> dict:
        try:
            return resp.json()
        except (json.JSONDecodeError, ValueError):
            raise PanError(f"响应解析失败（HTTP {resp.status_code}）")

    @staticmethod
    def set_cookie_values(resp_headers) -> list[str]:
        return [v for k, v in resp_headers.items() if k.lower() == "set-cookie"]


def build_proxy_kwargs() -> dict:
    proxy = get_proxy_with_detect()
    return {"proxy": proxy} if proxy else {}


def safe_name(name: str) -> str:
    """URL 片段安全化（仅用于日志与展示，不用于请求构造）。"""
    return quote(name[:80], safe="")
