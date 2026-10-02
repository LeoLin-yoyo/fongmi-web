"""代理配置测试：scheme 规范化 + 取值优先级（配置 → 环境变量 → 系统代理）"""
import json

import spider.proxy_config as pc


def _write_cfg(tmp_path, proxy):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"proxy": proxy}), encoding="utf-8")
    return str(p)


class TestNormalizeProxy:
    def test_add_http_scheme(self):
        assert pc._normalize_proxy("127.0.0.1:7890") == "http://127.0.0.1:7890"

    def test_keep_valid_schemes(self):
        assert pc._normalize_proxy("socks5://127.0.0.1:1080") == "socks5://127.0.0.1:1080"
        assert pc._normalize_proxy("http://127.0.0.1:7890") == "http://127.0.0.1:7890"

    def test_invalid_scheme_returns_empty(self):
        assert pc._normalize_proxy("ftp://example.com") == ""
        assert pc._normalize_proxy("") == ""
        assert pc._normalize_proxy(None) == ""

    def test_strip_whitespace(self):
        assert pc._normalize_proxy("  http://127.0.0.1:7890  ") == "http://127.0.0.1:7890"


class TestGetProxyPriority:
    def test_config_first(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pc, "_CONFIG_PATH", _write_cfg(tmp_path, "http://cfg:1"))
        monkeypatch.setattr(pc, "get_system_proxy", lambda: "http://sys:1")
        monkeypatch.setenv("HTTPS_PROXY", "http://env:1")
        assert pc.get_proxy() == "http://cfg:1"

    def test_env_second(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pc, "_CONFIG_PATH", _write_cfg(tmp_path, ""))
        monkeypatch.setattr(pc, "get_system_proxy", lambda: "http://sys:1")
        monkeypatch.setenv("HTTPS_PROXY", "http://env:1")
        assert pc.get_proxy() == "http://env:1"

    def test_system_proxy_last(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pc, "_CONFIG_PATH", _write_cfg(tmp_path, ""))
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.setattr(pc, "get_system_proxy", lambda: "http://sys:1")
        assert pc.get_proxy() == "http://sys:1"

    def test_all_empty_means_direct(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pc, "_CONFIG_PATH", _write_cfg(tmp_path, ""))
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.setattr(pc, "get_system_proxy", lambda: "")
        assert pc.get_proxy() == ""

    def test_config_scheme_normalized(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pc, "_CONFIG_PATH", _write_cfg(tmp_path, "127.0.0.1:7890"))
        assert pc.get_proxy() == "http://127.0.0.1:7890"

    def test_config_invalid_scheme_falls_through(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pc, "_CONFIG_PATH", _write_cfg(tmp_path, "ftp://bad"))
        monkeypatch.setattr(pc, "get_system_proxy", lambda: "http://sys:1")
        assert pc.get_proxy() == "http://sys:1"


class TestDetectLocalProxy:
    def test_detects_listening_port(self, tmp_path, monkeypatch):
        import socket
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        try:
            monkeypatch.setattr(pc, "_LOCAL_PROXY_PORTS", (port,))
            monkeypatch.setattr(pc, "_detected", None)
            monkeypatch.setattr(pc, "_detected_ts", 0.0)
            assert pc.detect_local_proxy() == f"http://127.0.0.1:{port}"
        finally:
            srv.close()

    def test_no_listener_returns_empty(self, monkeypatch):
        monkeypatch.setattr(pc, "_LOCAL_PROXY_PORTS", (1, 2))
        monkeypatch.setattr(pc, "_detected", None)
        monkeypatch.setattr(pc, "_detected_ts", 0.0)
        assert pc.detect_local_proxy() == ""

    def test_result_cached_within_ttl(self, tmp_path, monkeypatch):
        import socket
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        try:
            monkeypatch.setattr(pc, "_LOCAL_PROXY_PORTS", (port,))
            monkeypatch.setattr(pc, "_detected", None)
            monkeypatch.setattr(pc, "_detected_ts", 0.0)
            first = pc.detect_local_proxy()
            srv.close()  # 关掉监听，TTL 内仍应返回缓存值
            assert pc.detect_local_proxy() == first
        finally:
            srv.close()

    def test_get_proxy_with_detect_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pc, "_CONFIG_PATH", str(tmp_path / "absent.json"))
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.setattr(pc, "get_system_proxy", lambda: "")
        monkeypatch.setattr(pc, "detect_local_proxy", lambda: "http://127.0.0.1:7890")
        assert pc.get_proxy_with_detect() == "http://127.0.0.1:7890"

    def test_get_proxy_with_detect_prefers_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pc, "_CONFIG_PATH", _write_cfg(tmp_path, "http://cfg:1"))
        monkeypatch.setattr(pc, "detect_local_proxy", lambda: "http://127.0.0.1:7890")
        assert pc.get_proxy_with_detect() == "http://cfg:1"
