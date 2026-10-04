"""系统设置接口测试：external_player_path 持久化（data/config.json）与部分更新语义。"""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

import spider.proxy_config as pc
from api import system


def make_client():
    app = FastAPI()
    app.include_router(system.router, prefix="/api")
    return TestClient(app)


def test_external_player_path_roundtrip_persists(tmp_path, monkeypatch):
    """写入后即落盘到 config.json，GET 读回同一值——服务重启后仍在。"""
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(pc, "_CONFIG_PATH", str(cfg))
    c = make_client()

    r = c.post("/api/system/config", json={"external_player_path": r"D:\Players\PotPlayerMini64.exe"})
    assert r.status_code == 200
    assert json.loads(cfg.read_text(encoding="utf-8"))["external_player_path"] == r"D:\Players\PotPlayerMini64.exe"

    data = c.get("/api/system/config").json()["data"]
    assert data["external_player_path"] == r"D:\Players\PotPlayerMini64.exe"


def test_partial_update_keeps_other_keys(tmp_path, monkeypatch):
    """只传一个键时不得清空另一个键（此前 POST 全量覆盖 proxy 的行为收窄）。"""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"proxy": "http://127.0.0.1:7890"}), encoding="utf-8")
    monkeypatch.setattr(pc, "_CONFIG_PATH", str(cfg))
    c = make_client()

    c.post("/api/system/config", json={"external_player_path": r"C:\p\player.exe"})
    assert json.loads(cfg.read_text(encoding="utf-8"))["proxy"] == "http://127.0.0.1:7890"

    c.post("/api/system/config", json={"proxy": ""})
    assert json.loads(cfg.read_text(encoding="utf-8"))["external_player_path"] == r"C:\p\player.exe"


def test_post_strips_whitespace(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(pc, "_CONFIG_PATH", str(cfg))
    c = make_client()

    c.post("/api/system/config", json={"external_player_path": "  C:\\x\\player.exe  "})
    assert json.loads(cfg.read_text(encoding="utf-8"))["external_player_path"] == r"C:\x\player.exe"
