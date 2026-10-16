from fastapi import APIRouter
from api import config, vod, player, live, history as history_mod, image, system, live_source, metrics, downloads
from api import resources as resources_api
from pan import api as pan_api
from tg import api as tg_api

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
api_router.include_router(downloads.router)
api_router.include_router(pan_api.router)
api_router.include_router(tg_api.router)
api_router.include_router(resources_api.router)
