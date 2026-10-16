"""登录管控 REST API（挂载于 /api/auth）。

- GET  /api/auth/status  当前认证状态（公开）
- POST /api/auth/login   登录（公开，限速）
- POST /api/auth/logout  登出
- GET  /api/auth/config  读取配置（账号密码脱敏）
- POST /api/auth/config  写入配置（开启/关闭认证；开启时需已登录）
"""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from . import core

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = ""
    password: str = ""


class ConfigRequest(BaseModel):
    username: str = ""
    password: str = ""


def _set_cookie(response: Response, token: str, request: Request):
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(
        core.COOKIE_NAME, token,
        max_age=core.SESSION_TTL, httponly=True, samesite="lax",
        secure=secure, path="/",
    )


@router.get("/status")
async def status(request: Request):
    return {"code": 0, "data": core.session_status(request)}


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response):
    enabled, _, _ = core.load_config()
    if not enabled:
        return {"code": 0, "data": {"required": False, "authenticated": True}}
    ip = core.client_ip(request)
    remain = core.check_rate_limit(ip)
    if remain > 0:
        raise HTTPException(429, f"尝试过于频繁，请 {remain} 秒后重试")
    if not core.verify_credentials(body.username, body.password):
        core.record_failure(ip)
        raise HTTPException(401, "账号或密码错误")
    core.clear_failures(ip)
    token = core.create_token(body.username.strip())
    _set_cookie(response, token, request)
    return {"code": 0, "data": {"required": True, "authenticated": True,
                                "username": body.username.strip()}}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(core.COOKIE_NAME, path="/")
    return {"code": 0}


@router.get("/config")
async def get_config():
    enabled, username, password = core.load_config()
    return {"code": 0, "data": {
        "required": enabled,
        "username": username,
        "has_password": bool(password),
    }}


@router.post("/config")
async def set_config(body: ConfigRequest, request: Request):
    enabled, _, _ = core.load_config()
    # 已开启认证时，改配置必须先登录（防止被随意关闭）
    if enabled and not core.verify_token(request.cookies.get(core.COOKIE_NAME)):
        raise HTTPException(401, "请先登录后再修改登录配置")
    username = body.username.strip()
    password = body.password
    if bool(username) != bool(password):
        raise HTTPException(400, "账号与密码必须同时填写，或同时留空以关闭登录")
    core.save_config(username, password)
    return {"code": 0, "data": {"required": bool(username and password)}}
