"""异步 HTTP 客户端，替代原 OkHttp 网络层"""
import ipaddress
import os
import socket
import urllib.parse

import httpx
from loguru import logger


def ensure_http_url(url: str, *, allow_private: bool | None = None) -> str:
    """站点/资源 URL 的 SSRF 校验：协议白名单 + 解析后阻断私网/环回/链路本地地址。

    局域网自建 CMS、IPTV 源等内网场景需显式放行：
    设置环境变量 FONGMI_ALLOW_PRIVATE_NETWORK=1，或调用时传 allow_private=True
    （仅限 URL 为硬编码本机服务的场景）。
    """
    parts = urllib.parse.urlsplit(url or "")
    if parts.scheme.lower() not in ("http", "https"):
        raise ValueError(f"不支持的 URL 协议: {str(url)[:80]}")
    host = parts.hostname
    if not host:
        raise ValueError(f"URL 缺少主机: {str(url)[:80]}")
    if allow_private is None:
        allow_private = os.environ.get("FONGMI_ALLOW_PRIVATE_NETWORK", "") == "1"
    if allow_private:
        return url

    try:
        ips = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            ips = [ipaddress.ip_address(ai[4][0]) for ai in socket.getaddrinfo(host, None)]
        except (socket.gaierror, ValueError) as e:
            raise ValueError(f"域名解析失败: {host}") from e
    for ip in ips:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError(f"禁止访问内网地址: {host}")
    return url


def _build_client(proxy_url: str = "") -> httpx.AsyncClient:
    kwargs = dict(follow_redirects=True, timeout=30.0, verify=False)
    if proxy_url:
        kwargs["proxy"] = proxy_url
    return httpx.AsyncClient(**kwargs)


class NetClient:
    def __init__(self):
        self._proxy = ""
        self.client = _build_client()

    async def get(self, url, headers=None, params=None) -> str:
        resp = await self.client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.text

    async def post(self, url, data=None, headers=None) -> str:
        resp = await self.client.post(url, data=data, headers=headers)
        resp.raise_for_status()
        return resp.text

    async def get_bytes(self, url, headers=None) -> bytes:
        resp = await self.client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.content

    def set_proxy(self, proxy_url: str):
        self._proxy = proxy_url
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(1) as pool:
                    pool.submit(asyncio.run, self.client.aclose()).result(timeout=5)
            else:
                loop.run_until_complete(self.client.aclose())
        except Exception:
            pass
        self.client = _build_client(proxy_url)
        logger.info(f"Proxy set to {proxy_url}")

    async def close(self):
        await self.client.aclose()
