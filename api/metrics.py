"""播放/导航埋点基线（T0-1）

前端上报事件，按天落盘 JSONL（data/metrics/events-YYYYMMDD.jsonl），
提供 /metrics/summary 汇总与 /metrics/export 基线存档（baseline-YYYYMMDD.json）。
事件类型：
- ttff      首帧耗时 {ms, resolution}
- session   一次播放会话汇总 {play_ms, rebuffer_count, rebuffer_ms, completed}
- complete  播放完成 {duration_ms}
- nav       页面跳转 {from, to}
- error     播放器错误 {message}
"""
import json
import os
import re
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from loguru import logger

router = APIRouter(prefix="/metrics", tags=["metrics"])

_METRICS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "metrics")
_ALLOWED_TYPES = {"ttff", "session", "complete", "nav", "error"}
_MAX_EVENT_FILE_BYTES = 20 * 1024 * 1024


class MetricEvent(BaseModel):
    type: str
    sid: str = ""
    ts: int = Field(default=0)
    data: dict = Field(default_factory=dict)


def _today_file() -> str:
    return os.path.join(_METRICS_DIR, f"events-{datetime.now().strftime('%Y%m%d')}.jsonl")


def _iter_events():
    if not os.path.isdir(_METRICS_DIR):
        return
    for fname in sorted(os.listdir(_METRICS_DIR)):
        if not fname.startswith("events-") or not fname.endswith(".jsonl"):
            continue
        path = os.path.join(_METRICS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue


def _percentile(values: list, p: float) -> float:
    """线性插值百分位（与 numpy percentile 默认行为一致）"""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return round(float(s[0]), 2)
    pos = p / 100 * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return round(float(s[lo]) * (1 - frac) + float(s[hi]) * frac, 2)


@router.post("/event")
async def report_event(event: MetricEvent):
    if event.type not in _ALLOWED_TYPES:
        return {"code": 0, "ignored": True}
    try:
        os.makedirs(_METRICS_DIR, exist_ok=True)
        path = _today_file()
        # 单文件超限时轮转停止写入，避免磁盘被撑爆
        if os.path.exists(path) and os.path.getsize(path) > _MAX_EVENT_FILE_BYTES:
            return {"code": 0, "overflow": True}
        record = {
            "type": event.type,
            "sid": event.sid,
            "ts": event.ts or int(datetime.now().timestamp() * 1000),
            "data": event.data,
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"metrics write failed: {e}")
    return {"code": 0}


def _summary() -> dict:
    ttff_ms = []
    sessions = {"count": 0, "play_ms": 0.0, "rebuffer_count": 0, "rebuffer_ms": 0.0}
    completes = 0
    nav_steps = []
    errors = 0

    for ev in _iter_events():
        data = ev.get("data") or {}
        etype = ev.get("type")
        if etype == "ttff":
            ms = data.get("ms")
            if isinstance(ms, (int, float)) and ms > 0:
                ttff_ms.append(ms)
        elif etype == "session":
            sessions["count"] += 1
            sessions["play_ms"] += float(data.get("play_ms") or 0)
            sessions["rebuffer_count"] += int(data.get("rebuffer_count") or 0)
            sessions["rebuffer_ms"] += float(data.get("rebuffer_ms") or 0)
        elif etype == "complete":
            completes += 1
        elif etype == "nav":
            to = str(data.get("to") or "")
            frm = str(data.get("from") or "")
            if to.startswith("/play") or to.startswith("/local/player"):
                steps = 1 if frm == "/" else (2 if frm.startswith("/detail") else None)
                if steps:
                    nav_steps.append(steps)
        elif etype == "error":
            errors += 1

    rebuffer_total = sessions["rebuffer_ms"]
    total_watch = sessions["play_ms"] + rebuffer_total
    rebuffer_rate = round(rebuffer_total / total_watch, 4) if total_watch > 0 else 0.0

    try:
        from api.image import cache_stats
        img_cache = cache_stats()
    except Exception:
        img_cache = {}

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ttff": {
            "count": len(ttff_ms),
            "p50_ms": _percentile(ttff_ms, 50),
            "p95_ms": _percentile(ttff_ms, 95),
        },
        "playback": {
            "sessions": sessions["count"],
            "total_play_ms": round(sessions["play_ms"]),
            "rebuffer_count": sessions["rebuffer_count"],
            "rebuffer_ms": round(rebuffer_total),
            "rebuffer_rate": rebuffer_rate,
            "completes": completes,
            "complete_rate": round(completes / sessions["count"], 4) if sessions["count"] else 0.0,
        },
        "nav": {
            "home_to_play_samples": len(nav_steps),
            "steps_p95": _percentile(nav_steps, 95),
        },
        "player_errors": errors,
        "image_cache": img_cache,
    }


@router.get("/summary")
async def metrics_summary():
    return _summary()


@router.get("/export")
async def metrics_export():
    """存档当日基线 baseline-YYYYMMDD.json"""
    summary = _summary()
    os.makedirs(_METRICS_DIR, exist_ok=True)
    out = os.path.join(_METRICS_DIR, f"baseline-{datetime.now().strftime('%Y%m%d')}.json")
    from pathlib import Path
    Path(out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"code": 0, "file": out, "summary": summary}


@router.get("/raw")
async def metrics_raw(type: str = "", limit: int = 200):
    """按类型查看最近原始事件（排查用）"""
    pattern = re.compile(r"^[a-z]+$") if type else None
    if type and not pattern.match(type):
        return {"events": []}
    events = []
    for ev in _iter_events():
        if type and ev.get("type") != type:
            continue
        events.append(ev)
    return {"events": events[-limit:]}
