"""API 端到端测试。"""
import os
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from local_video import api as local_api
from local_video.db import Database
from local_video.scanner import Scanner
from local_video.state import app_state


@pytest.fixture
def client(tmp_path, sample_video):
    db = Database(str(tmp_path / "api.db"))
    scanner = Scanner(db)
    app_state.db = db
    app_state.scanner = scanner

    lib = tmp_path / "lib"
    lib.mkdir()
    shutil.copy2(sample_video, lib / "demo.mp4")
    db.add_dir(str(lib))
    scanner.scan_dir(str(lib))

    app = FastAPI()
    app.include_router(local_api.router, prefix="/api")
    return TestClient(app)


def test_health(client):
    r = client.get("/api/local/dirs")
    assert r.status_code == 200


def test_list_dirs(client):
    r = client.get("/api/local/dirs")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_add_dir_validation(client, tmp_path):
    r = client.post("/api/local/dirs", json={"path": str(tmp_path / "nope")})
    assert r.status_code == 400

    new_dir = tmp_path / "newlib"
    new_dir.mkdir()
    r = client.post("/api/local/dirs", json={"path": str(new_dir)})
    assert r.status_code == 200
    assert r.json()["path"] == str(new_dir)

    r = client.post("/api/local/dirs", json={"path": str(new_dir)})
    assert r.status_code == 200
    assert len(client.get("/api/local/dirs").json()) == 2


def test_delete_dir(client, tmp_path):
    dirs = client.get("/api/local/dirs").json()
    assert len(dirs) == 1
    r = client.delete(f"/api/local/dirs/{dirs[0]['id']}")
    assert r.status_code == 200
    assert client.get("/api/local/dirs").json() == []
    assert client.get("/api/local/videos").json()["total"] == 0


def test_list_videos_search_sort(client):
    data = client.get("/api/local/videos").json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "demo.mp4"

    data = client.get("/api/local/videos", params={"search": "zzz"}).json()
    assert data["total"] == 0


def test_list_videos_sort_by_mtime_default_desc(client, tmp_path, sample_video):
    lib = tmp_path / "lib2"
    lib.mkdir()
    import shutil
    old = lib / "old.mp4"
    new = lib / "new.mp4"
    shutil.copy2(sample_video, old)
    os.utime(old, (1000000000, 1000000000))
    shutil.copy2(sample_video, new)
    os.utime(new, (2000000000, 2000000000))
    app_state.db.add_dir(str(lib))
    app_state.scanner.scan_dir(str(lib))

    data = client.get("/api/local/videos", params={"sort": "mtime", "order": "desc"}).json()
    assert data["items"][0]["name"] == "new.mp4"
    assert data["items"][0]["mtime"] > data["items"][1]["mtime"]

    data = client.get("/api/local/videos", params={"sort": "mtime", "order": "asc"}).json()
    assert data["items"][0]["name"] == "old.mp4"


def test_stream_with_range(client):
    video = client.get("/api/local/videos").json()["items"][0]
    r = client.get(f"/api/local/videos/{video['id']}/stream", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206
    assert r.headers["content-range"].endswith(f"/{video['size']}")
    assert len(r.content) == 100


def test_stream_unknown_video(client):
    r = client.get("/api/local/videos/99999/stream")
    assert r.status_code == 404


def test_thumbnail_generated(client):
    video = client.get("/api/local/videos").json()["items"][0]
    r = client.get(f"/api/local/videos/{video['id']}/thumb")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert len(r.content) > 100
    assert r.headers["cache-control"].startswith("public")


def test_stats(client):
    r = client.get("/api/local/stats").json()
    assert r["video_count"] == 1
    assert r["dir_count"] == 1


def test_delete_videos_removes_files(client, tmp_path, sample_video):
    lib = tmp_path / "del_lib"
    lib.mkdir()
    import shutil
    v = lib / "to_delete.mp4"
    shutil.copy2(sample_video, v)
    app_state.db.add_dir(str(lib))
    app_state.scanner.scan_dir(str(lib))

    rows = app_state.db.list_videos()
    vid = next(r for r in rows if r["path"] == str(v))
    assert v.exists()

    r = client.request("DELETE", f"/api/local/videos?ids={vid['id']}")
    assert r.status_code == 200
    data = r.json()
    assert data["deleted"] == 1
    assert not v.exists()
    assert app_state.db.get_video(vid["id"]) is None

    r2 = client.request("DELETE", "/api/local/videos?ids=abc")
    assert r2.status_code == 400


def test_delete_videos_missing_file(client, tmp_path, sample_video):
    lib = tmp_path / "del_lib2"
    lib.mkdir()
    import shutil
    v = lib / "gone.mp4"
    shutil.copy2(sample_video, v)
    app_state.db.add_dir(str(lib))
    app_state.scanner.scan_dir(str(lib))
    vid = app_state.db.get_video_by_path(str(v))
    os.remove(v)

    r = client.request("DELETE", f"/api/local/videos?ids={vid['id']}")
    assert r.status_code == 200
    data = r.json()
    assert data["deleted"] == 0 and data["missing"] == 1
    assert app_state.db.get_video(vid["id"]) is None
