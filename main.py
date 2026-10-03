import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import json as json_mod
from loguru import logger

from model.database import init_db
from api import api_router
from local_video import api as local_api
from local_video.state import init_local_video

FRONTEND_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    init_local_video()
    yield


app = FastAPI(title="FongMi TV Web", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"code": 1, "detail": "请求参数错误: " + str(exc.errors())},
    )


@app.exception_handler(json_mod.JSONDecodeError)
async def json_decode_handler(request: Request, exc: json_mod.JSONDecodeError):
    return JSONResponse(
        status_code=400,
        content={"code": 1, "detail": "JSON 格式错误"},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, (SystemExit, KeyboardInterrupt, GeneratorExit)):
        raise exc
    logger.opt(exception=exc).error(f"Unhandled error on {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"code": 1, "detail": "服务器内部错误"},
    )

# API routes first
app.include_router(api_router, prefix="/api")
app.include_router(local_api.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"code": 0, "status": "ok"}


# Serve static assets BEFORE the SPA fallback
if os.path.isdir(os.path.join(FRONTEND_DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")


@app.get("/")
async def root():
    index_file = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index_file):
        # 入口页必须禁缓存：否则浏览器启发式缓存旧 index.html，构建更新后继续引用已删除的旧 chunk
        return FileResponse(index_file, headers={"Cache-Control": "no-cache"})
    return JSONResponse({"code": 0, "msg": "FongMi TV Web"})


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    # Don't catch API or assets routes
    if full_path.startswith(("api/", "assets/")):
        raise HTTPException(404)
    index_file = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file, headers={"Cache-Control": "no-cache"})
    raise HTTPException(404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
