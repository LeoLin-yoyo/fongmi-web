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


def test_reorder_dirs(client, tmp_path):
    for i in range(2):
        d = tmp_path / f"ord{i}"
        d.mkdir()
        client.post("/api/local/dirs", json={"path": str(d)})
    original = [d["id"] for d in client.get("/api/local/dirs").json()]
    assert len(original) == 3

    reordered = list(reversed(original))
    r = client.put("/api/local/dirs/order", json={"ids": reordered})
    assert r.status_code == 200
    assert [d["id"] for d in r.json()["dirs"]] == reordered
    assert [d["id"] for d in client.get("/api/local/dirs").json()] == reordered

    # 新增目录排到队尾
    tail = tmp_path / "ord_tail"
    tail.mkdir()
    client.post("/api/local/dirs", json={"path": str(tail)})
    ids = [d["id"] for d in client.get("/api/local/dirs").json()]
    assert ids[:3] == reordered

    # 传入 ID 集合与现有目录不一致 → 400，顺序不变
    r = client.put("/api/local/dirs/order", json={"ids": original[:1]})
    assert r.status_code == 400
    r = client.put("/api/local/dirs/order", json={"ids": "bad"})
    assert r.status_code == 400
    assert [d["id"] for d in client.get("/api/local/dirs").json()] == ids


def test_migrate_old_dirs_schema(tmp_path):
    """旧版数据库（dirs 无 sort_order 列）启动时自动迁移，顺序保持 id 序。"""
    import sqlite3

    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE dirs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            added_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            last_scan TEXT
        );
        INSERT INTO dirs (path, name) VALUES ('C:\\a', 'a'), ('C:\\b', 'b');
        """
    )
    conn.commit()
    conn.close()

    db = Database(str(db_path))
    assert [d["name"] for d in db.list_dirs()] == ["a", "b"]
    assert db.reorder_dirs([2, 1])
    assert [d["id"] for d in db.list_dirs()] == [2, 1]
    assert not db.reorder_dirs([1])


def test_dir_groups_crud_and_filter(client, tmp_path, sample_video):
    lib_a = tmp_path / "ga"
    lib_b = tmp_path / "gb"
    lib_a.mkdir()
    lib_b.mkdir()
    shutil.copy2(sample_video, lib_a / "a.mp4")
    shutil.copy2(sample_video, lib_b / "b.mp4")
    shutil.copy2(sample_video, lib_b / "b2.mp4")
    app_state.db.add_dir(str(lib_a))
    app_state.db.add_dir(str(lib_b))
    app_state.scanner.scan_dir(str(lib_a))
    app_state.scanner.scan_dir(str(lib_b))
    dirs = client.get("/api/local/dirs").json()
    path_to_id = {d["path"]: d["id"] for d in dirs}
    id_a, id_b = path_to_id[str(lib_a)], path_to_id[str(lib_b)]

    # 校验：目录不足 2 个 / 名称为空 / 目录不存在 / 目录重复
    r = client.post("/api/local/groups", json={"name": "X", "dir_ids": [id_a]})
    assert r.status_code == 400
    r = client.post("/api/local/groups", json={"name": "", "dir_ids": [id_a, id_b]})
    assert r.status_code == 400
    r = client.post("/api/local/groups", json={"name": "X", "dir_ids": [id_a, 99999]})
    assert r.status_code == 400
    r = client.post("/api/local/groups", json={"name": "X", "dir_ids": [id_a, id_a]})
    assert r.status_code == 400

    # 创建：ga(1) + gb(2) 合并查询 = 3 个视频
    r = client.post("/api/local/groups", json={"name": "合并库", "dir_ids": [id_a, id_b]})
    assert r.status_code == 200
    group = r.json()
    assert group["name"] == "合并库"
    assert sorted(group["dir_ids"]) == sorted([id_a, id_b])
    assert any(g["id"] == group["id"] for g in client.get("/api/local/groups").json())

    data = client.get("/api/local/videos", params={"group_id": group["id"]}).json()
    assert data["total"] == 3
    assert {v["name"] for v in data["items"]} == {"a.mp4", "b.mp4", "b2.mp4"}

    # dir_id 与 group_id 互斥
    r = client.get("/api/local/videos", params={"group_id": group["id"], "dir_id": id_a})
    assert r.status_code == 400

    # 更新：换目录集合 + 改名
    id_lib = path_to_id[next(p for p in path_to_id if p.endswith("lib"))]
    r = client.put(f"/api/local/groups/{group['id']}", json={"name": "改名", "dir_ids": [id_lib, id_b]})
    assert r.status_code == 200
    assert r.json()["name"] == "改名"
    data = client.get("/api/local/videos", params={"group_id": group["id"]}).json()
    assert data["total"] == 3
    assert {v["name"] for v in data["items"]} == {"demo.mp4", "b.mp4", "b2.mp4"}

    # 不存在的组 → 空结果而非报错；删除后 404
    assert client.get("/api/local/videos", params={"group_id": 99999}).json()["total"] == 0
    assert client.delete(f"/api/local/groups/{group['id']}").status_code == 200
    assert client.delete(f"/api/local/groups/{group['id']}").status_code == 404
    assert client.put(f"/api/local/groups/{group['id']}", json={"name": "x", "dir_ids": [id_a, id_b]}).status_code == 404


def test_delete_dir_cleans_groups(client, tmp_path):
    db = app_state.db
    a = db.add_dir(str(tmp_path / "ca"))
    b = db.add_dir(str(tmp_path / "cb"))
    (tmp_path / "ca").mkdir()
    (tmp_path / "cb").mkdir()
    g = db.create_group("G", [a["id"], b["id"]])
    assert g and sorted(g["dir_ids"]) == sorted([a["id"], b["id"]])

    r = client.delete(f"/api/local/dirs/{a['id']}")
    assert r.status_code == 200
    g2 = db.get_group(g["id"])
    assert g2 is not None and g2["dir_ids"] == [b["id"]]


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


def test_dir_visible_toggle(client, tmp_path):
    """目录可隐藏/显示；隐藏不影响扫描、视频查询与聚合。"""
    lib = tmp_path / "vis_lib"
    lib.mkdir()
    app_state.db.add_dir(str(lib))
    dirs = client.get("/api/local/dirs").json()
    d = dirs[0]
    assert d["visible"] == 1  # 默认可见

    # 参数校验与 404
    assert client.patch(f"/api/local/dirs/{d['id']}/visible", json={"visible": "yes"}).status_code == 400
    assert client.patch("/api/local/dirs/99999/visible", json={"visible": False}).status_code == 404

    # 隐藏
    r = client.patch(f"/api/local/dirs/{d['id']}/visible", json={"visible": False})
    assert r.status_code == 200 and r.json()["visible"] == 0
    assert client.get("/api/local/dirs").json()[0]["visible"] == 0

    # 隐藏后视频仍可查询、目录仍可扫描
    assert client.get("/api/local/videos", params={"dir_id": d["id"]}).json()["total"] == 1
    assert client.post(f"/api/local/dirs/{d['id']}/scan").status_code == 200

    # 恢复显示
    r = client.patch(f"/api/local/dirs/{d['id']}/visible", json={"visible": True})
    assert r.status_code == 200 and r.json()["visible"] == 1


def test_hidden_dir_still_aggregatable(client, tmp_path):
    """隐藏目录仍可被聚合选项卡包含，且组内视频照常合并返回。"""
    db = app_state.db
    a_dir = tmp_path / "hid_a"
    b_dir = tmp_path / "hid_b"
    a_dir.mkdir()
    b_dir.mkdir()
    a = db.add_dir(str(a_dir))
    b = db.add_dir(str(b_dir))
    db.set_dir_visible(a["id"], False)

    g = db.create_group("含隐藏", [a["id"], b["id"]])
    assert g is not None
    # 组内包含隐藏目录，查询仍正常（无视频时为空集，不报错）
    r = client.get("/api/local/videos", params={"group_id": g["id"]})
    assert r.status_code == 200 and r.json()["total"] == 0


def test_migrate_old_dirs_schema_adds_visible(tmp_path):
    """旧库（无 visible 列）迁移后 visible 默认 1。"""
    import sqlite3

    db_path = tmp_path / "old_vis.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE dirs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            added_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            last_scan TEXT
        );
        INSERT INTO dirs (path, name) VALUES ('C:\\v1', 'v1');
        """
    )
    conn.commit()
    conn.close()

    db = Database(str(db_path))
    rows = db.list_dirs()
    assert rows[0]["visible"] == 1
    assert db.set_dir_visible(rows[0]["id"], False)["visible"] == 0


# ---- 外部播放器调用 ----

def _setup_player(tmp_path, monkeypatch, exe="fake_player.exe"):
    """隔离 config.json 并写入一个存在的假播放器路径，返回其绝对路径。"""
    import spider.proxy_config as pc
    monkeypatch.setattr(pc, "_CONFIG_PATH", str(tmp_path / "config.json"))
    player = tmp_path / exe
    player.write_bytes(b"MZ")
    pc.set_config_value("external_player_path", str(player))
    return str(player)


def test_external_play_requires_config(client, tmp_path, monkeypatch):
    import spider.proxy_config as pc
    monkeypatch.setattr(pc, "_CONFIG_PATH", str(tmp_path / "config.json"))
    video = client.get("/api/local/videos").json()["items"][0]
    r = client.post(f"/api/local/videos/{video['id']}/external-play")
    assert r.status_code == 400
    assert "尚未配置" in r.json()["detail"]


def test_external_play_player_path_missing(client, tmp_path, monkeypatch):
    import spider.proxy_config as pc
    monkeypatch.setattr(pc, "_CONFIG_PATH", str(tmp_path / "config.json"))
    pc.set_config_value("external_player_path", str(tmp_path / "nope.exe"))
    video = client.get("/api/local/videos").json()["items"][0]
    r = client.post(f"/api/local/videos/{video['id']}/external-play")
    assert r.status_code == 400
    assert "不存在" in r.json()["detail"]


def test_external_play_video_not_found(client, tmp_path, monkeypatch):
    _setup_player(tmp_path, monkeypatch)
    r = client.post("/api/local/videos/99999/external-play")
    assert r.status_code == 404


def test_external_play_file_gone(client, tmp_path, monkeypatch):
    _setup_player(tmp_path, monkeypatch)
    video = client.get("/api/local/videos").json()["items"][0]
    os.remove(video["path"])
    r = client.post(f"/api/local/videos/{video['id']}/external-play")
    assert r.status_code == 404
    assert "移动或删除" in r.json()["detail"]


def test_external_play_launches_player(client, tmp_path, monkeypatch):
    player = _setup_player(tmp_path, monkeypatch)
    video = client.get("/api/local/videos").json()["items"][0]
    calls = []

    import ctypes

    def fake_shell_execute(hwnd, verb, exe, params, directory, show):
        calls.append((exe, params))
        return 42  # >32 视为成功

    monkeypatch.setattr(ctypes.windll.shell32, "ShellExecuteW", fake_shell_execute)
    r = client.post(f"/api/local/videos/{video['id']}/external-play")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert len(calls) == 1
    exe, params = calls[0]
    assert exe == player
    assert video["path"] in params  # 视频完整路径作为参数传给播放器


def test_external_play_shellexecute_failure(client, tmp_path, monkeypatch):
    _setup_player(tmp_path, monkeypatch)
    video = client.get("/api/local/videos").json()["items"][0]
    import ctypes
    monkeypatch.setattr(ctypes.windll.shell32, "ShellExecuteW", lambda *a: 2)  # SE_ERR_FNF
    r = client.post(f"/api/local/videos/{video['id']}/external-play")
    assert r.status_code == 500
    assert "ShellExecute" in r.json()["detail"]
