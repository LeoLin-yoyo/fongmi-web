"""System Settings API (proxy, external player, etc.)"""
from fastapi import APIRouter

from spider.proxy_config import get_config_value, get_proxy, set_config_value, set_proxy

router = APIRouter()


@router.get("/system/config")
async def get_config():
    return {
        "code": 0,
        "data": {
            "proxy": get_proxy(),
            "external_player_path": get_config_value("external_player_path"),
        },
    }


@router.post("/system/config")
async def update_config(body: dict):
    # 只更新请求里出现的键，避免保存单项设置时把其他配置清空
    if "proxy" in body:
        set_proxy(body.get("proxy", ""))
    if "external_player_path" in body:
        set_config_value("external_player_path", str(body.get("external_player_path") or "").strip())
    return {"code": 0}
