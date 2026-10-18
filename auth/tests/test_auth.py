"""登录管控测试：配置读取、令牌、限速、路径判定、API 行为。"""
import json
import os
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import core


@pytest.fixture(autouse=True)
def clean_auth(tmp_path, monkeypatch):
    """每个测试用独立的 auth.json 与密钥，互不干扰。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(core, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(core, "AUTH_FILE", str(data_dir / "auth.json"))
    monkeypatch.setattr(core, "_SECRET_DIR", str(data_dir / ".secret"))
    monkeypatch.setattr(core, "_SECRET_FILE", str(data_dir / ".secret" / "auth.key"))
    core._cfg_cache = {"mtime": None, "data": (False, "", "")}
    core._fails.clear()
    yield


def _write_auth(username, password):
    fd = os.open(core.AUTH_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"username": username, "password": password}, f)
    core._cfg_cache["mtime"] = None


# ---------- 配置 ----------

def test_disabled_when_file_missing():
    enabled, u, p = core.load_config()
    assert enabled is False and u == "" and p == ""
    assert core.is_enabled() is False


@pytest.mark.parametrize("u,p", [("", ""), ("admin", ""), ("", "pass"), ("  ", "pass")])
def test_disabled_when_credentials_empty(u, p):
    _write_auth(u, p)
    assert core.is_enabled() is False


def test_enabled_with_both_fields():
    _write_auth("admin", "secret")
    assert core.is_enabled() is True
    assert core.load_config() == (True, "admin", "secret")


def test_malformed_json_is_disabled():
    fd = os.open(core.AUTH_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("{not json")
    core._cfg_cache["mtime"] = None
    assert core.is_enabled() is False


def test_save_config_roundtrip():
    core.save_config("bob", "pw123")
    assert core.load_config() == (True, "bob", "pw123")
    core.save_config("", "")
    assert core.is_enabled() is False


# ---------- 令牌 ----------

def test_token_roundtrip():
    _write_auth("admin", "secret")
    token = core.create_token("admin")
    payload = core.verify_token(token)
    assert payload and payload["u"] == "admin"


def test_token_tamper_rejected():
    _write_auth("admin", "secret")
    token = core.create_token("admin")
    body, _, sig = token.rpartition(".")
    assert core.verify_token(f"{body}.{'0' * len(sig)}") is None
    assert core.verify_token("garbage") is None
    assert core.verify_token(None) is None


def test_token_expiry():
    _write_auth("admin", "secret")
    now = int(time.time())
    payload = {"u": "admin", "iat": now - 100, "exp": now - 1}
    import base64, hmac, hashlib
    body = core._b64e(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(core._secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    assert core.verify_token(f"{body}.{sig}") is None


# ---------- 凭据校验 ----------

def test_verify_credentials():
    _write_auth("admin", "secret")
    assert core.verify_credentials("admin", "secret") is True
    assert core.verify_credentials("admin", "wrong") is False
    assert core.verify_credentials("nobody", "secret") is False
    assert core.verify_credentials("", "") is False


def test_verify_when_disabled_always_false():
    assert core.verify_credentials("admin", "secret") is False


# ---------- 限速 ----------

def test_rate_limit_lockout():
    ip = "1.2.3.4"
    assert core.check_rate_limit(ip) == 0
    for _ in range(core._MAX_FAILS):
        core.record_failure(ip)
    assert core.check_rate_limit(ip) > 0
    core.clear_failures(ip)
    assert core.check_rate_limit(ip) == 0


# ---------- 路径判定 ----------

@pytest.mark.parametrize("path", ["/api/auth/status", "/api/auth/login", "/assets/x.js", "/login", "/api/health"])
def test_public_paths(path):
    assert core.is_public_path(path) is True


@pytest.mark.parametrize("path", ["/", "/setting", "/api/pan/platforms", "/api/local/videos"])
def test_protected_paths(path):
    assert core.is_public_path(path) is False


# ---------- API 行为 ----------

@pytest.fixture
def client(monkeypatch):
    from auth import api as auth_api

    app = FastAPI()
    # router 自带 prefix="/auth"，挂到 /api 下即 /api/auth/*
    app.include_router(auth_api.router, prefix="/api")
    return TestClient(app)


def test_api_status_when_disabled(client):
    r = client.get("/api/auth/status")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["required"] is False and d["authenticated"] is True


def test_api_login_flow(client):
    _write_auth("admin", "secret")
    # 错误密码
    assert client.post("/api/auth/login", json={"username": "admin", "password": "x"}).status_code == 401
    # 正确登录
    r = client.post("/api/auth/login", json={"username": "admin", "password": "secret"})
    assert r.status_code == 200
    assert "fongmi_session" in r.cookies
    # 状态
    st = client.get("/api/auth/status").json()["data"]
    assert st["required"] is True and st["authenticated"] is True


def test_api_login_rate_limited(client):
    _write_auth("admin", "secret")
    for _ in range(core._MAX_FAILS):
        client.post("/api/auth/login", json={"username": "admin", "password": "x"})
    r = client.post("/api/auth/login", json={"username": "admin", "password": "secret"})
    assert r.status_code == 429


def test_api_logout(client):
    _write_auth("admin", "secret")
    client.post("/api/auth/login", json={"username": "admin", "password": "secret"})
    client.post("/api/auth/logout")
    st = client.get("/api/auth/status").json()["data"]
    assert st["authenticated"] is False


def test_api_config_requires_login_when_enabled(client):
    _write_auth("admin", "secret")
    # 未登录不能改配置
    assert client.post("/api/auth/config", json={"username": "", "password": ""}).status_code == 401
    # 登录后可关闭
    client.post("/api/auth/login", json={"username": "admin", "password": "secret"})
    r = client.post("/api/auth/config", json={"username": "", "password": ""})
    assert r.status_code == 200
    assert core.is_enabled() is False


def test_api_config_partial_rejected(client):
    _write_auth("admin", "secret")
    client.post("/api/auth/login", json={"username": "admin", "password": "secret"})
    r = client.post("/api/auth/config", json={"username": "newuser", "password": ""})
    assert r.status_code == 400
