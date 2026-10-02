from fastapi import APIRouter
from api import config, vod, player, live, history as history_mod, image, system, live_source, metrics

api_router = APIRouter()

# Each sub-router includes its own prefix
api_router.include_router(vod.router)
api_router.include_router(player.router)
api_router.include_router(live.router)
api_router.include_router(history_mod.router)
api_router.include_router(config.router, prefix="/config")
api_router.include_router(image.router)
api_router.include_router(system.router)
api_router.include_router(live_source.router, prefix="/live_source")
api_router.include_router(metrics.router)
