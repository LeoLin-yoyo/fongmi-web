"""下载引擎单元测试：分块、断点续传、sidecar 原子写、文件名校验。"""
import asyncio
import os
import shutil
import tempfile

import pytest
import httpx

from downloader import engine, journal
from downloader.engine import (
    FileDownloader,
    FatalDownloadError,
    filename_from_disposition,
    parse_content_range_total,
    sanitize_filename,
    resolve_target,
)


def test_sanitize_filename():
    assert sanitize_filename('a/b\\c:d*e?f"g<h>i|j.mp4') == "a_b_c_d_e_f_g_h_i_j.mp4"
    assert sanitize_filename("  trailing.  ") == "trailing"
    assert sanitize_filename("CON.mp4") == "_CON.mp4"       # Windows 保留名
    assert sanitize_filename("") == "download.bin"
    assert len(sanitize_filename("x" * 500 + ".mp4")) <= 200


def test_resolve_target_collision(tmp_path):
    # 同名不同大小 → 追加 (2)
    p1 = tmp_path / "movie.mp4"
    p1.write_bytes(b"a" * 10)
    got = resolve_target(str(tmp_path), "movie.mp4", 999)
    assert got.endswith("movie (2).mp4")
    # 同名同大小 → 复用
    assert resolve_target(str(tmp_path), "movie.mp4", 10) == str(p1)


def test_parse_content_range_total():
    assert parse_content_range_total("bytes 0-99/12345") == 12345
    assert parse_content_range_total("") == 0


def test_filename_from_disposition():
    assert filename_from_disposition('attachment; filename="a.mp4"') == "a.mp4"
    assert filename_from_disposition("attachment; filename*=UTF-8''%E7%94%B5%E5%BD%B1.mp4") == "电影.mp4"
    # latin1 错送的 UTF-8 还原
    raw = "电影.mp4".encode("utf-8").decode("latin-1")
    assert filename_from_disposition(f'attachment; filename="{raw}"') == "电影.mp4"


def test_journal_roundtrip(tmp_path):
    final = str(tmp_path / "f.bin")
    meta = {"size": 100, "block": 10, "done": [0, 1], "partial": {"2": 3}}
    journal.write_meta(final, meta)
    got = journal.read_meta(final)
    assert got["size"] == 100 and got["done"] == [0, 1]
    assert got["partial"] == {"2": 3}
    journal.delete_meta(final)
    assert journal.read_meta(final) is None


def test_done_bytes():
    # 100 字节、块 10：完成块 0-2 = 30 字节，块 3 半块 4 字节
    assert journal.done_bytes(100, 10, {0, 1, 2}, {3: 4}) == 34


def test_missing_blocks():
    assert journal.missing_blocks(100, 10, {0, 2}) == [1, 3, 4, 5, 6, 7, 8, 9]


# ---------- 引擎端到端（本地 Range 服务器） ----------

class _RangeHandler:
    pass


@pytest.fixture(scope="module")
def range_server():
    import http.server
    import re

    DATA = bytes(range(256)) * (12 * 1024)  # 3 MiB

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(DATA)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

        def do_GET(self):
            rng = self.headers.get("Range")
            if rng:
                m = re.match(r"bytes=(\d+)-(\d+)", rng)
                s, e = int(m.group(1)), min(int(m.group(2)), len(DATA) - 1)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {s}-{e}/{len(DATA)}")
                self.send_header("Content-Length", str(e - s + 1))
                self.end_headers()
                self.wfile.write(DATA[s:e + 1])
            else:
                self.send_response(200)
                self.send_header("Content-Length", str(len(DATA)))
                self.end_headers()
                self.wfile.write(DATA)

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    import threading
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_full_download(range_server, tmp_path):
    async def go():
        client = httpx.AsyncClient(follow_redirects=False, verify=False, timeout=30)
        dl = FileDownloader(client, f"{range_server}/v.mp4", str(tmp_path),
                            block=512 * 1024, connections=4)
        path = await dl.run()
        await client.aclose()
        return path
    path = _run(go())
    assert os.path.getsize(path) == 3 * 1024 * 1024
    assert not os.path.isfile(path + ".part")
    assert not os.path.isfile(path + ".part.meta.json")


def test_resume_from_partial(range_server, tmp_path):
    """预置前 2 块已完成的 sidecar，续传应只补剩余块。"""
    async def go():
        client = httpx.AsyncClient(follow_redirects=False, verify=False, timeout=30)
        url = f"{range_server}/r.mp4"
        # 先完整下前两块
        dl = FileDownloader(client, url, str(tmp_path), block=512 * 1024, connections=1)
        dl.total = await dl.probe()
        dl._resolve_final()
        dl._prep_part()
        dl._fh = open(journal.part_path(dl.final), "r+b")
        for i in (0, 1):
            await dl._fetch_block(i)
        dl._save_meta()
        dl._fh.close()
        assert dl.done == {0, 1}

        # 再起一个新实例：应识别 sidecar 并续传
        dl2 = FileDownloader(client, url, str(tmp_path), block=512 * 1024, connections=4)
        path = await dl2.run()
        await client.aclose()
        assert dl2.done == set(range(6))
        return path
    path = _run(go())
    assert os.path.getsize(path) == 3 * 1024 * 1024
