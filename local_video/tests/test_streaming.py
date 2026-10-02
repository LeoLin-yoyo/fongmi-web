"""Range 头解析与分块响应测试。"""
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from local_video.streaming import parse_range, stream_video


@pytest.mark.parametrize(
    "header,size,expected",
    [
        (None, 1000, None),
        ("bytes=0-499", 1000, (0, 499)),
        ("bytes=500-", 1000, (500, 999)),
        ("bytes=-100", 1000, (900, 999)),
        ("bytes=0-0", 1, (0, 0)),
        ("bytes=999-", 1000, (999, 999)),
        ("bytes=-0", 1000, None),
        ("bytes=1000-", 1000, None),
        ("bytes=abc", 1000, None),
        ("bytes=10-5", 1000, None),
        ("", 1000, None),
    ],
)
def test_parse_range(header, size, expected):
    assert parse_range(header, size) == expected


@pytest.fixture
def video_file(tmp_path):
    p = tmp_path / "v.mp4"
    p.write_bytes(bytes(range(256)) * 40)
    return p


@pytest.fixture
def client(video_file):
    app = FastAPI()

    @app.get("/v/{name}")
    def route(name: str, range_header: str | None = None):
        return stream_video(video_file, "video/mp4", range_header)

    return TestClient(app)


def test_full_response(client):
    r = client.get("/v/x", headers={})
    assert r.status_code == 200
    assert r.headers.get("content-length") == "10240"
    assert len(r.content) == 10240


def test_partial_response(client):
    r = client.get("/v/x", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206
    assert r.headers["content-range"] == "bytes 0-99/10240"
    assert r.headers["content-length"] == "100"
    assert r.content == bytes(range(256))[:100]


def test_suffix_range(client):
    r = client.get("/v/x", headers={"Range": "bytes=-512"})
    assert r.status_code == 206
    assert r.headers["content-range"] == "bytes 9728-10239/10240"
    assert r.content == (bytes(range(256)) * 40)[9728:]


def test_out_of_range(client):
    r = client.get("/v/x", headers={"Range": "bytes=20000-"})
    assert r.status_code == 416
    assert r.headers["content-range"] == "bytes */10240"


def test_middle_chunk_consistency(client):
    r = client.get("/v/x", headers={"Range": "bytes=3000-3999"})
    assert r.status_code == 206
    assert r.content == (bytes(range(256)) * 40)[3000:4000]
