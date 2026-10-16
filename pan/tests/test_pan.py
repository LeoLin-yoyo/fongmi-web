"""网盘模块单元测试：链接识别、Cookie 工具、加密、直链签发与流代理。"""
import asyncio
import json
import tempfile
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pan import crypto, resolver
from pan.cookies import merge_from_set_cookies, pugs_from_set_cookies, without_puus
from pan.link import detect_platform, parse_share_link
from pan.models import DownloadLink


# ---------- 链接识别 ----------

@pytest.mark.parametrize("text,platform,share_id,passcode", [
    ("https://pan.quark.cn/s/abc123def 提取码：wxyz", "quark", "abc123def", "wxyz"),
    ("https://drive.uc.cn/s/xyz789?pwd=abcd", "uc", "xyz789", "abcd"),
    ("https://pan.xunlei.com/s/ABC_-123 密码: 9999", "xunlei", "ABC_-123", "9999"),
    ("https://pan.baidu.com/s/1AbCdEf 提取码：1234", "baidu", "AbCdEf", "1234"),
    ("https://yun.139.com/shareweb/#/w/i/abcDEF", "c139", "abcDEF", ""),
    ("https://123pan.com/s/AbC1-DEfG", "pan123", "AbC1-DEfG", ""),
    ("https://guangyapan.com/s/AbC-dEf", "guangya", "AbC-dEf", ""),
    ("https://example.ilanzou.com/s/abc_123", "ilanzou", "abc_123", ""),
])
def test_parse_share_link(text, platform, share_id, passcode):
    s = parse_share_link(text)
    assert s is not None
    assert s.platform == platform
    assert s.share_id == share_id
    assert s.passcode == passcode


def test_parse_115_command_form():
    """115 口令形态 /swxxxxx-nnnn/：后段是提取码。"""
    s = parse_share_link("https://115.com/sws8lxs36jf-n307/")
    assert s.platform == "pan115"
    assert s.share_id == "sws8lxs36jf"
    assert s.passcode == "n307"


def test_parse_115_share_link():
    s = parse_share_link("https://115cdn.com/s/swabc123 访问码：a1b2")
    assert s.platform == "pan115"
    assert s.share_id == "swabc123"
    assert s.passcode == "a1b2"


def test_parse_lanzou_variants():
    for host in ("wwa.lanzoui.com", "pan.lanzou.com", "wws.lanzoux.com"):
        s = parse_share_link(f"https://{host}/i123456")
        assert s and s.platform == "lanzou"


def test_parse_no_link():
    assert parse_share_link("随便一段文字没有链接") is None
    assert detect_platform("没有链接") == ""


def test_ilanzou_takes_priority_over_lanzou():
    s = parse_share_link("https://example.ilanzou.com/s/abc_123")
    assert s.platform == "ilanzou"


# ---------- Cookie 工具 ----------

def test_merge_from_set_cookies():
    original = "__pus=old; other=1"
    merged = merge_from_set_cookies(original, ["__puus=newpuus; Path=/", "junk=2"])
    assert "__puus=newpuus" in merged
    assert "other=1" in merged
    assert "junk=2" not in merged  # 非跟踪字段不并入


def test_merge_overrides_same_key():
    merged = merge_from_set_cookies("__puus=old", ["__puus=new; Path=/"])
    assert merged == "__puus=new"


def test_without_puus():
    assert without_puus("__pus=a; __puus=b; c=d") == "__pus=a; c=d"


def test_pugs_from_set_cookies():
    got = pugs_from_set_cookies(["__pugs=token123; Domain=quark.cn", "x=y"])
    assert got == "__pugs=token123"
    assert pugs_from_set_cookies(["nothing=1"]) is None


# ---------- 加密 ----------

def test_crypto_roundtrip():
    plain = "Cookie: __pus=secret; __puus=alsosecret"
    enc = crypto.encrypt(plain)
    assert enc.startswith("gcm1:") and enc != plain
    assert crypto.decrypt(enc) == plain


def test_crypto_context_binding():
    enc = crypto.encrypt("data", context="ctx.a")
    with pytest.raises(Exception):
        crypto.decrypt(enc, context="ctx.b")


def test_crypto_plaintext_passthrough():
    assert crypto.decrypt("legacy-plain") == "legacy-plain"


# ---------- 直链签发 + 流代理 ----------

@pytest.fixture
def client():
    from pan import api as pan_api
    app = FastAPI()
    app.include_router(pan_api.router, prefix="/api")
    return TestClient(app)


def _inject(token: str, link: DownloadLink):
    resolver._LINKS[token] = (link, 1e18)


def test_link_info_and_expiry(client):
    _inject("tk1", DownloadLink(fid="f", filename="电影.mp4", url="http://127.0.0.1:1/x.mp4", size=100))
    r = client.get("/api/pan/info/tk1")
    assert r.status_code == 200
    assert r.json()["playable"] is True

    r2 = client.get("/api/pan/info/unknown")
    assert r2.status_code == 410


def test_playable_flag(client):
    _inject("mkv1", DownloadLink(filename="movie.mkv", url="http://127.0.0.1:1/x", size=10))
    assert client.get("/api/pan/info/mkv1").json()["playable"] is False


def test_stream_head_headers(client):
    _inject("hd1", DownloadLink(fid="f", filename="v.mp4",
                                url="http://127.0.0.1:8899/x.mp4", size=3 * 1024 * 1024))
    r = client.head("/api/pan/stream/hd1")
    assert r.status_code == 200
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-length"] == str(3 * 1024 * 1024)


def test_stream_head_range(client):
    _inject("hd2", DownloadLink(fid="f", filename="v.mp4",
                                url="http://127.0.0.1:8899/x.mp4", size=3 * 1024 * 1024))
    r = client.head("/api/pan/stream/hd2", headers={"Range": "bytes=100-199"})
    assert r.status_code == 206
    assert r.headers["content-range"] == "bytes 100-199/3145728"
    assert r.headers["content-length"] == "100"


def test_platforms_endpoint(client):
    r = client.get("/api/pan/platforms")
    keys = {p["key"] for p in r.json()["data"]}
    assert {"quark", "uc", "xunlei", "baidu", "c139", "pan123", "pan115", "guangya", "lanzou", "ilanzou"} <= keys


def test_resolve_bad_link(client):
    r = client.post("/api/pan/resolve", json={"text": "没有链接"})
    assert r.status_code == 400
