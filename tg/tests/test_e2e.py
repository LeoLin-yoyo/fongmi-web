"""TG 模块端到端测试：用 mock tdl 忠实模拟 serve/chat/login 接口。

mock tdl 脚本内联在本文件，测试时写入临时目录并赋予可执行权限。
覆盖：会话列表、serve 会话建立、块缓存内容校验、跨块 Range、流代理 HTTP 语义。
"""
import asyncio
import os
import stat
import sys
import textwrap

import pytest

MOCK_TDL = r'''#!/usr/bin/env python3
import sys, json, re, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

FILES = [
    {"peer": 1001, "msg": 1, "name": "预告片.mp4", "size": 3*1024*1024},
    {"peer": 1001, "msg": 2, "name": "正片.mkv", "size": 3*1024*1024},
    {"peer": 1002, "msg": 3, "name": "document.pdf", "size": 512*1024},
]
UNIT = 512*1024

def content(seed, size):
    return bytes((i*7+seed) % 256 for i in range(size))

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _find(self):
        m = re.match(r"^/(\d+)/(\d+)", self.path)
        if not m: return None
        for f in FILES:
            if f["peer"]==int(m.group(1)) and f["msg"]==int(m.group(2)): return f
        return None
    def do_HEAD(self):
        f = self._find()
        if not f: self.send_response(404); self.end_headers(); return
        from urllib.parse import quote
        self.send_response(200)
        self.send_header("Content-Length", str(f["size"]))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Disposition", "attachment; filename*=UTF-8''"+quote(f["name"]))
        self.end_headers()
    def do_GET(self):
        if self.path in ("/", ""):
            html = "".join('<a href="%d/%d">%s</a>' % (f["peer"], f["msg"], f["name"]) for f in FILES)
            b = html.encode(); self.send_response(200)
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        f = self._find()
        if not f: self.send_response(404); self.end_headers(); return
        data = content(f["msg"], f["size"])
        rng = self.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\d+)-(\d+)?", rng); s = int(m.group(1))
            e = int(m.group(2)) if m.group(2) else f["size"]-1; e = min(e, f["size"]-1)
            a0 = (s//UNIT)*UNIT; a1 = min(((e//UNIT)+1)*UNIT-1, f["size"]-1)
            self.send_response(206)
            self.send_header("Content-Range", "bytes %d-%d/%d" % (a0, a1, f["size"]))
            self.send_header("Content-Length", str(a1-a0+1)); self.end_headers()
            self.wfile.write(data[a0:a1+1])
        else:
            self.send_response(200); self.send_header("Content-Length", str(f["size"]))
            self.end_headers(); self.wfile.write(data)

class S(ThreadingMixIn, HTTPServer):
    daemon_threads = True; allow_reuse_address = True

args = sys.argv[1:]
i = 0
while i < len(args) and args[i].startswith("--"):
    i += 2
args = args[i:]
if not args: print("mock"); sys.exit(0)
if args[0] == "dl":
    port = int(args[args.index("--port")+1])
    S(("127.0.0.1", port), H).serve_forever()
elif args[0] == "chat":
    print(json.dumps([{"id":1001,"name":"测试频道","username":"testchannel"}]))
elif args[0] == "login":
    print("Enter Code:", end="", flush=True)
    time.sleep(0.5)
    print("\nLogin successfully! ID: 999, Username: testuser", flush=True)
else:
    print("unknown")
'''


@pytest.fixture
def mock_tdl(tmp_path):
    p = tmp_path / "tdl"
    p.write_text(MOCK_TDL)
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(p)


@pytest.fixture
def tg_env(mock_tdl, tmp_path):
    from tg.config import save_config
    save_config({"tdl_path": mock_tdl, "download_dir": str(tmp_path / "dl"),
                 "stream_connections": 4})
    yield
    # 清理：停掉所有 serve 会话
    from tg.serve import serve_manager
    asyncio.get_event_loop().run_until_complete(serve_manager.stop_all()) if False else None


def _run(coro):
    return asyncio.run(coro)


def test_mock_chat_ls(tg_env):
    from tg.session import invalidate, list_chats
    invalidate()
    chats = _run(list_chats(refresh=True))
    assert chats and chats[0]["name"] == "测试频道"


def test_serve_session_and_blocks(tg_env, tmp_path):
    from tg.serve import serve_manager
    from tg.stream import get_streamer

    async def go():
        sess = await serve_manager.start(["https://t.me/testchannel/123"], str(tmp_path / "dl"))
        assert sess.state == "ready", sess.error
        assert len(sess.files) == 3
        names = {f["name"] for f in sess.files}
        assert "预告片.mp4" in names and "正片.mkv" in names and "document.pdf" in names
        mp4 = next(f for f in sess.files if f["name"].endswith(".mp4"))
        assert mp4["playable"] is True
        pdf = next(f for f in sess.files if f["name"].endswith(".pdf"))
        assert pdf["playable"] is False

        st = get_streamer(sess, mp4["href"], mp4["size"])
        data = await st.block(0)
        expected = bytes(((i * 7 + mp4["msg"]) % 256) for i in range(len(data)))
        assert data == expected, "块内容必须逐字节一致"

        # 跨块范围
        got = b""
        async for piece in st.iter_range(500 * 1024, 2500 * 1024):
            got += piece
        want_len = 2500 * 1024 - 500 * 1024 + 1
        assert len(got) == want_len
        base = mp4["msg"]
        assert got[0] == (500 * 1024 * 7 + base) % 256

        await serve_manager.stop(sess.sid)
        assert serve_manager.get(sess.sid) is None

    _run(go())


def test_streamer_range_slice(tg_env, tmp_path):
    """流代理的 iter_range 必须精确裁剪到请求范围（浏览器协议要求）。"""
    from tg.serve import serve_manager
    from tg.stream import get_streamer

    async def go():
        sess = await serve_manager.start(["https://t.me/x/1"], str(tmp_path / "dl"))
        assert sess.state == "ready"
        f = next(x for x in sess.files if x["name"].endswith(".mp4"))
        st = get_streamer(sess, f["href"], f["size"])
        got = b""
        async for piece in st.iter_range(1000, 1999):
            got += piece
        assert len(got) == 1000
        await serve_manager.stop(sess.sid)

    _run(go())


def test_tdl_locate_and_status(tg_env, mock_tdl):
    from tg.runner import runner
    assert runner.locate(mock_tdl) == mock_tdl
    from tg.tdlfetch import status
    assert status()["hasTdl"] is True
