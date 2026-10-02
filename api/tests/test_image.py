"""图片代理测试：代理配置路由 + 失败回退直连 + 降级占位 + 缓存命中"""
import pytest

import api.image as image_mod


class FakeResponse:
    def __init__(self, content=b"x" * 200, content_type="image/jpeg"):
        self.content = content
        self.headers = {"content-type": content_type}


class FakeAsyncClient:
    """捕获构造参数，模拟成功拉图"""
    last_kwargs = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        FakeAsyncClient.last_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        return FakeResponse()


class DeadClient(FakeAsyncClient):
    async def get(self, url):
        raise RuntimeError("connection dead")


class ProxyDeadDirectOkClient(FakeAsyncClient):
    """走代理时失败（模拟代理不通），直连成功"""
    async def get(self, url):
        if self.kwargs.get("proxy"):
            raise RuntimeError("proxy dead")
        return FakeResponse()


@pytest.fixture(autouse=True)
def clean_cache():
    with image_mod._cache_lock:
        image_mod._cache.clear()
    yield
    with image_mod._cache_lock:
        image_mod._cache.clear()


class TestImageProxyRouting:
    def test_uses_configured_proxy(self, client, monkeypatch):
        monkeypatch.setattr(image_mod, "get_proxy_with_detect", lambda: "http://127.0.0.1:7890")
        monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)
        r = client.get("/api/img/proxy", params={"url": "https://example.com/a.jpg", "name": "测试"})
        assert r.status_code == 200
        assert FakeAsyncClient.last_kwargs.get("proxy") == "http://127.0.0.1:7890"

    def test_direct_when_no_proxy(self, client, monkeypatch):
        monkeypatch.setattr(image_mod, "get_proxy_with_detect", lambda: "")
        monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)
        r = client.get("/api/img/proxy", params={"url": "https://example.com/b.jpg"})
        assert r.status_code == 200
        assert FakeAsyncClient.last_kwargs.get("proxy") is None


class TestImageProxyFallback:
    def test_retry_direct_when_proxy_dead(self, client, monkeypatch):
        """代理拉取失败时回退直连重试，最终成功返回真图"""
        monkeypatch.setattr(image_mod, "get_proxy_with_detect", lambda: "http://127.0.0.1:9")
        monkeypatch.setattr("httpx.AsyncClient", ProxyDeadDirectOkClient)
        r = client.get("/api/img/proxy", params={"url": "https://example.com/retry.jpg"})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/jpeg")
        assert FakeAsyncClient.last_kwargs.get("proxy") is None

    def test_placeholder_on_fetch_error(self, client, monkeypatch):
        """代理与直连全部失败时降级占位 SVG"""
        monkeypatch.setattr(image_mod, "get_proxy_with_detect", lambda: "http://127.0.0.1:9")
        monkeypatch.setattr("httpx.AsyncClient", DeadClient)
        r = client.get("/api/img/proxy", params={"url": "https://example.com/c.jpg", "name": "庆余年"})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/svg+xml")
        assert "庆余年".encode("utf-8") in r.content

    def test_cache_hit_skips_client(self, client, monkeypatch):
        monkeypatch.setattr(image_mod, "get_proxy_with_detect", lambda: "")
        monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)
        url = "https://example.com/cached.jpg"
        r1 = client.get("/api/img/proxy", params={"url": url})
        assert r1.status_code == 200
        FakeAsyncClient.last_kwargs = None
        r2 = client.get("/api/img/proxy", params={"url": url})
        assert r2.status_code == 200
        assert FakeAsyncClient.last_kwargs is None
