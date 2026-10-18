"""Telegram 模块测试：链接净化、进度解析、配置。"""
import pytest

from tg.config import TgConfig, get_config, save_config
from tg.link import extract_links, parse_tg_link, sanitize_link
from tg.runner import classify_line, parse_size, sanitize_args, split_message, strip_ansi


# ---------- 链接净化 ----------

@pytest.mark.parametrize("raw,expected", [
    ("https://t.me/channel/123", "https://t.me/channel/123"),
    ("t.me/channel/123", "https://t.me/channel/123"),
    ("https://t.me/c/1234567890/55", "https://t.me/c/1234567890/55"),
    ("https://t.me/channel/123/45", "https://t.me/channel/123/45"),
    ("https://telegram.me/group/1", "https://t.me/group/1"),
])
def test_sanitize_valid(raw, expected):
    assert sanitize_link(raw) == expected


@pytest.mark.parametrize("raw", [
    "https://evil.com/t.me/channel/1",
    "https://t.me:8080/channel/1",
    "https://user:pass@t.me/channel/1",
    "https://t.me/",
    "https://t.me/channel/abc",
    "https://t.me/joinchat/xxxx",
    "not a link",
])
def test_sanitize_rejects(raw):
    assert sanitize_link(raw) is None


def test_parse_tg_link():
    link = parse_tg_link("https://t.me/mychannel/123?single")
    assert link.peer == "mychannel" and link.msg_id == 123
    l2 = parse_tg_link("https://t.me/c/987654/21/9")
    assert l2.peer == "987654" and l2.msg_id == 21 and l2.topic_id == 9
    assert l2.normalized() == "https://t.me/c/987654/21/9"


def test_extract_links():
    text = "看这个 https://t.me/aaa/1 还有 https://t.me/aaa/1 和 https://t.me/bbb/2 结尾"
    links = extract_links(text)
    assert links == ["https://t.me/aaa/1", "https://t.me/bbb/2"]  # 去重保序


# ---------- ANSI / 参数 ----------

def test_strip_ansi():
    assert strip_ansi("\x1b[31mhello\x1b[0m") == "hello"
    assert strip_ansi("a\x1b]0;title\x07b") == "ab"


def test_sanitize_args():
    assert sanitize_args(["a\x00b", "c\x1bd", "ok"]) == ["ab", "cd", "ok"]


# ---------- 大小 / 消息 ----------

def test_parse_size():
    assert parse_size("640.00KB") == int(640 * 1024)
    assert parse_size("1.5MB") == int(1.5 * 1024 ** 2)
    assert parse_size("100B") == 100
    assert parse_size("") == 0


def test_split_message():
    label, path = split_message("Channel(123):45 -> F:\\telegram\\video.mp4")
    assert label == "Channel(123):45"
    assert path == "F:\\telegram\\video.mp4"
    assert split_message("no arrow here") == ("no arrow here", "")


# ---------- 进度行解析（go-pretty 口径） ----------

def test_classify_done():
    r = classify_line("video.mp4 ... done! [1.50GB in 2m10s; 11.8MB/s]")
    assert r["kind"] == "itemDone"
    assert r["size"] == int(1.5 * 1024 ** 3)
    assert r["elapsed"] == "2m10s"


def test_classify_progress():
    r = classify_line("video.mp4 45.30% [######    ] [700.00MB in 1m30s; ~ETA: 1m20s; 8.00MB/s]")
    assert r["kind"] == "itemProgress"
    assert r["pct"] == 45.30
    assert r["done_bytes"] == int(700 * 1024 ** 2)
    assert abs(r["total"] - int(700 * 1024 ** 2 / 0.453)) < 1000
    assert r["speed_bps"] == 8 * 1024 ** 2


def test_classify_progress_with_path():
    line = "Ch(1):2 ... 10.00% [##        ] [1.00MB in 1s; ~ETA: 9s; 1.00MB/s] -> F:\\dl\\a.mp4"
    r = classify_line(line)
    assert r["kind"] == "itemProgress"
    assert r["path"] == "F:\\dl\\a.mp4"


def test_classify_failed():
    r = classify_line("bad.mp4 ... failed! [timeout]")
    assert r["kind"] == "itemFailed"
    assert r["tail"] == "timeout"


def test_classify_overall_ignored():
    assert classify_line("[####      ] [50%]")["kind"] == "overall"


def test_classify_ansi_wrapped():
    r = classify_line("\x1b[32mfile.mp4 ... done! [100MB in 5s]\x1b[0m")
    assert r["kind"] == "itemDone"


def test_classify_log():
    r = classify_line("some random log output")
    assert r["kind"] == "log"


# ---------- 配置 ----------

def test_config_clamp(monkeypatch):
    save_config({"stream_window_mb": 99999, "stream_cache_mb": 1, "connections": 999})
    cfg = get_config()
    assert cfg.stream_window_mb <= 4096
    assert cfg.stream_cache_mb >= 32
    assert cfg.connections <= 64


# ---------- serve 索引 / 路径安全 ----------

def test_parse_href():
    from tg.serve import parse_href
    assert parse_href("123/456") == (123, 456)
    assert parse_href("-1/2") is None
    assert parse_href("abc/456") is None
    assert parse_href("123") is None
    assert parse_href("") is None


def test_parse_index():
    from tg.serve import parse_index
    html = '<a href="1/2">a</a> <a href="3/4">b</a> <a href="x">c</a>'
    assert parse_index(html) == ["1/2", "3/4", "x"]


def test_ext_pair_case():
    from tg.serve import _ext_pair
    got = _ext_pair("mp4,mkv")
    assert "mp4" in got and "MP4" in got and "mkv" in got and "MKV" in got


def test_is_playable_and_mime():
    from tg.serve import is_playable, mime_of
    assert is_playable("a.mp4") is True
    assert is_playable("a.mkv") is True
    assert is_playable("a.zip") is False
    assert mime_of("a.mp4") == "video/mp4"
    assert mime_of("a.bin") == "application/octet-stream"


def test_filename_from_headers():
    from tg.serve import _filename_from_headers

    class H:
        def __init__(self, d): self._d = d
        def get(self, k, default=None): return self._d.get(k.lower(), default)

    assert _filename_from_headers(H({"content-disposition": 'attachment; filename="a.mp4"'})) == "a.mp4"
    assert _filename_from_headers(H({"content-disposition": "attachment; filename*=UTF-8''%E7%94%B5%E5%BD%B1.mp4"})) == "电影.mp4"
    raw = "电影.mp4".encode("utf-8").decode("latin-1")
    assert _filename_from_headers(H({"content-disposition": f'attachment; filename="{raw}"'})) == "电影.mp4"


# ---------- Range 解析 ----------

def test_range_parse():
    from tg.stream import parse_range
    assert parse_range("bytes=0-1023", 10000) == (0, 1023)
    assert parse_range("bytes=500-", 10000) == (500, 9999)
    assert parse_range("bytes=-500", 10000) == (9500, 9999)
    assert parse_range("bytes=99999-", 10000) is None
    assert parse_range("bytes=100-50", 10000) is None
    assert parse_range(None, 10000) is None
    assert parse_range("garbage", 10000) is None
    # 多段只取第一段
    assert parse_range("bytes=0-99,200-299", 10000) == (0, 99)
    # 越界末端裁剪
    assert parse_range("bytes=9000-20000", 10000) == (9000, 9999)


def test_sanitize_link_from_config_roundtrip():
    save_config({"ns": "myns", "connections": 12})
    cfg = get_config()
    assert cfg.ns == "myns" and cfg.connections == 12


# ---------- 播放会话保活 / 防误杀 ----------

def _clear_streamers():
    from tg import stream
    stream._streamers.clear()


def _make_streamer(sid: str, href: str, last_hit: float):
    from tg.stream import FileStreamer, _streamers
    st = object.__new__(FileStreamer)
    st.sid, st.href, st.last_hit = sid, href, last_hit
    _streamers[f"{sid}:{href}"] = st
    return st


def test_is_playing_detects_active_streamer():
    import time
    from tg.api import _is_playing
    _clear_streamers()
    st = _make_streamer("sid1", "1/2", time.time() - 600)
    assert _is_playing("sid1") is False
    st.last_hit = time.time()
    assert _is_playing("sid1") is True
    _clear_streamers()


def test_active_stream_keys_only_recent():
    import time
    from tg.stream import active_stream_keys
    _clear_streamers()
    _make_streamer("a", "1/1", time.time())
    _make_streamer("b", "1/1", time.time() - 600)
    keys = active_stream_keys(timeout=60.0)
    assert "a:1/1" in keys and "b:1/1" not in keys
    _clear_streamers()


def test_reap_idle_skips_playing():
    import asyncio
    import time
    from tg.serve import ServeManager, ServeSession
    from tg.stream import FileStreamer
    _clear_streamers()

    mgr = ServeManager()
    for sid, idle in (("idle", 600.0), ("busy", 600.0), ("fresh", 1.0)):
        ss = object.__new__(ServeSession)
        ss.sid, ss.port, ss.base, ss.dir = sid, 0, "", ""
        ss.proc, ss.files, ss.state = None, [], "ready"
        ss.last_used = time.time() - idle
        mgr.sessions[sid] = ss
    _make_streamer("busy", "1/1", time.time())

    stopped = []

    async def fake_stop(sid):
        stopped.append(sid)
        mgr.sessions.pop(sid, None)
        return True
    mgr.stop = fake_stop

    reaped = asyncio.run(mgr.reap_idle(timeout=300.0))
    assert "idle" in reaped and "busy" not in reaped and "fresh" not in reaped
    assert set(stopped) == {"idle"}
    _clear_streamers()


def test_session_idle_seconds():
    import time
    from tg.serve import ServeSession
    ss = object.__new__(ServeSession)
    ss.last_used = time.time() - 42.0
    assert 41.0 <= ss.idle_seconds() <= 43.0


def test_stop_session_refused_while_playing():
    """正在播放的会话不能被 stop 误杀（「重新解析」/「关闭会话」都走这里）。"""
    import time
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from tg.api import _play_sessions, _cur_play, router
    from tg.serve import ServeManager, ServeSession
    import tg.api as tg_api
    _clear_streamers()

    mgr = ServeManager()
    ss = object.__new__(ServeSession)
    ss.sid, ss.port, ss.base, ss.dir = "play1", 0, "", ""
    ss.proc, ss.files, ss.state = None, [], "ready"
    ss.last_used = time.time()
    mgr.sessions["play1"] = ss
    tg_api._saved_mgr = tg_api.serve_manager
    tg_api.serve_manager = mgr

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    _make_streamer("play1", "1/1", __import__("time").time())

    try:
        _play_sessions["play1"] = {"urls": [], "files": []}
        _cur_play["sid"] = "play1"
        r = client.post("/tg/session/play1/stop")
        assert r.status_code == 409
        assert "播放" in r.json()["detail"]
        assert mgr.get("play1") is not None, "播放中的会话必须保留"
    finally:
        tg_api.serve_manager = tg_api._saved_mgr
        del tg_api._saved_mgr
        _play_sessions.pop("play1", None)
        _cur_play["sid"] = ""
        _clear_streamers()


def test_preview_keeps_playing_and_reaps_rest():
    """preview 保留正在播放的会话，同时回收其它非播放会话（防泄漏）。"""
    import time
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from tg.api import _play_sessions, _cur_play, router
    from tg.serve import ServeManager, ServeSession
    import tg.api as tg_api
    _clear_streamers()

    mgr = ServeManager()
    for sid in ("playing", "stale"):
        ss = object.__new__(ServeSession)
        ss.sid, ss.port, ss.base, ss.dir = sid, 0, "", ""
        ss.proc, ss.files, ss.state = None, [], "ready"
        ss.last_used = time.time() - 600.0
        mgr.sessions[sid] = ss
    tg_api.serve_manager, tg_api._saved_mgr = mgr, tg_api.serve_manager

    async def fake_stop(sid):
        mgr.sessions.pop(sid, None)
        return True
    mgr.stop = fake_stop

    async def fake_start(self, urls, out_dir, sid=""):
        ss = object.__new__(ServeSession)
        ss.sid, ss.port, ss.base, ss.dir = "newone", 0, "", ""
        ss.proc, ss.files, ss.state, ss.error = None, [], "ready", ""
        ss.last_used = time.time()
        mgr.sessions["newone"] = ss
        return ss
    mgr.start = lambda urls, out_dir, sid="": fake_start(mgr, urls, out_dir, sid)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    try:
        _play_sessions["playing"] = {"urls": [], "files": []}
        _cur_play["sid"] = "stale"          # 前一次 stop 后残留的 sid
        _make_streamer("playing", "1/1", time.time())
        r = client.post("/tg/preview", json={"urls": "https://t.me/c/123/45"})
        assert r.status_code == 200, r.text
        assert mgr.get("playing") is not None, "播放中的会话不被回收"
        assert mgr.get("stale") is None, "非播放会话应被回收"
        assert mgr.get("newone") is not None
        assert _cur_play["sid"] == "newone"
    finally:
        tg_api.serve_manager = tg_api._saved_mgr
        del tg_api._saved_mgr
        _play_sessions.clear()
        _cur_play["sid"] = ""
        _clear_streamers()


def test_keepalive_endpoint():
    """keepalive 对存在的会话续期并返回 idle；对已关闭的会话返回 404。"""
    import time
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from tg.api import router
    from tg.serve import ServeManager, ServeSession
    import tg.api as tg_api

    mgr = ServeManager()
    ss = object.__new__(ServeSession)
    ss.sid, ss.port, ss.base, ss.dir = "ka1", 0, "", ""
    ss.proc, ss.files, ss.state = None, [], "ready"
    ss.last_used = time.time() - 120.0
    mgr.sessions["ka1"] = ss
    tg_api._saved_mgr = tg_api.serve_manager
    tg_api.serve_manager = mgr

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    try:
        r = client.post("/tg/keepalive/ka1")
        assert r.status_code == 200
        assert r.json()["data"]["sid"] == "ka1"
        assert ss.idle_seconds() < 5.0, "keepalive 必须续期 last_used"
        assert client.post("/tg/keepalive/nosuch").status_code == 404
    finally:
        tg_api.serve_manager = tg_api._saved_mgr
        del tg_api._saved_mgr
