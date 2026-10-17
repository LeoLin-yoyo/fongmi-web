"""抖音模块测试：链接识别、页面 JSON 提取、作品解析、无水印替换、API 行为。"""
import json
from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from douyin import link, parser, resolver
from douyin.parser import DouyinError, extract_page_json, find_aweme, no_watermark, parse_aweme, parse_page


# ---------- 链接识别 ----------

@pytest.mark.parametrize("text,expected_id", [
    ("https://v.douyin.com/iABCdef/", None),                        # 短链需重定向
    ("https://www.douyin.com/video/7300000000000000000", "7300000000000000000"),
    ("https://www.iesdouyin.com/share/video/7300000000000000001/", "7300000000000000001"),
    ("https://www.iesdouyin.com/share/slides/7300000000000000002", "7300000000000000002"),
    ("https://m.douyin.com/note/7300000000000000003", "7300000000000000003"),
    ("https://www.douyin.com/7300000000000000004", "7300000000000000004"),
])
def test_extract_and_parse_id(text, expected_id):
    url = link.extract_url(text)
    assert url
    assert link.parse_aweme_id(url) == expected_id


def test_extract_from_share_text():
    """分享口令里夹带链接与中文标点。"""
    text = "7.43 复制打开抖音，看看【某作者】的作品 https://v.douyin.com/iABCdef/ 复制此链接"
    assert link.extract_url(text) == "https://v.douyin.com/iABCdef"


def test_extract_no_link():
    assert link.extract_url("没有链接的一段话") is None
    assert link.extract_url("") is None


# ---------- 页面 JSON 提取 ----------

def _router_html(payload: dict) -> str:
    return ("<html><script>window._ROUTER_DATA = "
            + json.dumps(payload, ensure_ascii=False) + ";</script></html>")


def test_extract_router_data():
    payload = {"loaderData": {"video_(id)/page": {"videoInfoRes": {"item_list": [{"desc": "标题"}]}}}}
    got = extract_page_json(_router_html(payload))
    assert got["loaderData"]["video_(id)/page"]["videoInfoRes"]["item_list"][0]["desc"] == "标题"


def test_extract_router_data_with_nested_braces():
    """JSON 内含嵌套对象与字符串花括号，需正确配对。"""
    payload = {"a": {"b": {"desc": "带 } 和 { 的文案", "n": {"x": 1}}}}
    got = extract_page_json(_router_html(payload))
    assert got["a"]["b"]["desc"] == "带 } 和 { 的文案"


def test_extract_render_data():
    payload = {"aweme": {"desc": "RENDER"}}
    html = ('<html><script id="RENDER_DATA" type="application/json">'
            + quote(json.dumps(payload, ensure_ascii=False)) + "</script></html>")
    got = extract_page_json(html)
    assert got["aweme"]["desc"] == "RENDER"


def test_extract_no_data():
    assert extract_page_json("<html><body>no data</body></html>") is None
    assert extract_page_json("") is None


# ---------- 作品解析 ----------

def _video_payload(**over) -> dict:
    item = {
        "aweme_id": "7300000000000000000",
        "desc": "测试视频标题",
        "author": {"nickname": "某作者"},
        "video": {
            "play_addr": {"url_list": [
                "https://aweme.snssdk.com/aweme/v1/playwm/?video_id=v0300&ratio=720p"]},
            "cover": {"url_list": ["https://p3.douyinpic.com/cover.jpg"]},
        },
        "music": {"play_url": {"url_list": ["https://sf3.douyinstatic.com/music.mp3"]}},
    }
    item.update(over)
    return {"loaderData": {"video_(id)/page": {"videoInfoRes": {"item_list": [item]}}}}


def test_parse_video():
    info = parse_aweme(_video_payload())
    assert info["type"] == "video"
    assert info["title"] == "测试视频标题"
    assert info["author"] == "某作者"
    assert "playwm" in info["video_url"]
    assert info["cover_url"].endswith("cover.jpg")
    assert info["music_url"].endswith("music.mp3")


def test_parse_images():
    payload = _video_payload(images=[
        {"url_list": ["https://p3.douyinpic.com/1.jpg"]},
        {"url_list": ["https://p3.douyinpic.com/2.jpg"]},
    ])
    info = parse_aweme(payload)
    assert info["type"] == "images"
    assert info["images"] == ["https://p3.douyinpic.com/1.jpg",
                              "https://p3.douyinpic.com/2.jpg"]


def test_no_watermark():
    assert no_watermark("https://x/aweme/v1/playwm/?a=1") == "https://x/aweme/v1/play/?a=1"
    assert no_watermark("https://x/playwm") == "https://x/play"
    assert no_watermark("") == ""


def test_find_aweme_direct():
    """顶层就是作品对象时也能识别。"""
    obj = {"desc": "直接", "video": {"play_addr": {"url_list": ["https://a/b.mp4"]}}}
    assert find_aweme(obj) is obj


def test_parse_page_dead_video():
    """页面有作品结构但 videoInfoRes 为 None → 判为不存在/私密。"""
    payload = {"loaderData": {"video_(id)/page": None}}
    html = _router_html(payload)
    # 该形态没有 videoInfoRes，属于「平台未返回数据」而非「作品不存在」
    with pytest.raises(DouyinError, match="风控|Cookie|uifid"):
        parse_page(html)


def test_parse_page_dead_video_with_marker():
    """item_list 为空 → 属于「平台未返回作品数据」，走风控提示。"""
    html = ('<html><script>window._ROUTER_DATA = {"loaderData":'
            '{"video_(id)/page":{"videoInfoRes":{"item_list":[]}}}};</script></html>')
    with pytest.raises(DouyinError, match="风控|uifid|Cookie"):
        parse_page(html)


def test_parse_page_dead_video_null_res():
    """videoInfoRes 为 null 且无 item_list → 风控提示。"""
    html = ('<html><script>window._ROUTER_DATA = {"loaderData":'
            '{"video_(id)/page":{"videoInfoRes":null}}};</script></html>')
    with pytest.raises(DouyinError, match="风控|uifid|Cookie"):
        parse_page(html)


def test_parse_page_no_data():
    with pytest.raises(DouyinError, match="风控|Cookie|uifid"):
        parse_page("<html><body>blocked</body></html>")


def test_parse_page_unknown_type():
    """有作品数据但既无视频也无图集 → 未能识别类型。"""
    payload = {"loaderData": {"x": {"desc": "只有标题", "videoInfoRes": {"item_list": [{"desc": "只有标题"}]}}}}
    with pytest.raises(DouyinError, match="未能识别作品类型"):
        parse_page(_router_html(payload))


# ---------- token 签发 ----------

def test_token_issue_and_expire():
    token = resolver._issue("https://cdn/x.mp4", "video", "a.mp4")
    got = resolver.take_link(token)
    assert got["url"] == "https://cdn/x.mp4" and got["kind"] == "video"
    # 未知 token
    assert resolver.take_link("nope") is None
    # 过期
    resolver._LINKS[token] = ("u", "video", "a.mp4", 0)
    assert resolver.take_link(token) is None


# ---------- API ----------

@pytest.fixture
def client():
    from douyin import api as douyin_api

    app = FastAPI()
    app.include_router(douyin_api.router, prefix="/api")
    return TestClient(app)


def test_api_resolve_empty(client):
    r = client.post("/api/douyin/resolve", json={"text": ""})
    assert r.status_code == 400


def test_api_resolve_no_link(client):
    r = client.post("/api/douyin/resolve", json={"text": "没有链接"})
    assert r.status_code == 422
    assert "未找到抖音链接" in r.json()["detail"]


def test_api_stream_expired(client):
    r = client.get("/api/douyin/stream/unknowntoken")
    assert r.status_code == 410


def test_api_config_roundtrip(client, monkeypatch):
    import douyin.api as api_mod
    store = {"v": ""}
    monkeypatch.setattr(api_mod, "get_config_value", lambda k, d="": store["v"])
    monkeypatch.setattr(api_mod, "set_config_value", lambda k, v: store.update(v=v))
    assert client.post("/api/douyin/config", json={"cookie": "abc=1"}).status_code == 200
    assert store["v"] == "abc=1"
    assert client.get("/api/douyin/config").json()["data"]["has_cookie"] is True


# ---------- SM3（国密标准测试向量） ----------

def test_sm3_standard_vectors():
    from douyin.sm3 import sm3_hash
    # GB/T 32905-2016 附录 A
    assert sm3_hash(b"abc") == \
        "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0"
    assert sm3_hash(b"abcd" * 16) == \
        "debe9ff92275b8a138604889c18e5a4d6fdb70e5387e5765293dcba39c0c5732"


# ---------- a_bogus 签名 ----------

def test_abogus_generates():
    from douyin.abogus import ABogus
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36"
    sig = ABogus(ua).get_value("aweme_id=123&aid=6383", "GET")
    assert isinstance(sig, str) and len(sig) > 60
    # 只应包含自定义字母表内的字符
    from douyin.abogus import _ALPHABET
    assert all(ch in _ALPHABET for ch in sig)


def test_abogus_deterministic_shape():
    """同一 UA 多次签名长度稳定（内容含时间戳，故值不同）。"""
    from douyin.abogus import ABogus
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0"
    ab = ABogus(ua)
    a = ab.get_value("x=1", "GET", start_time=1700000000000, end_time=1700000000005)
    b = ab.get_value("x=1", "GET", start_time=1700000000000, end_time=1700000000005)
    assert len(a) == len(b)


def test_abogus_sign_query():
    from douyin.abogus import sign_query
    out = sign_query("a=1&b=2", "Mozilla/5.0")
    assert out.startswith("a=1&b=2&a_bogus=")
    assert "%2F" in out or "%2B" in out or "%3D" in out  # 已 URL 编码
