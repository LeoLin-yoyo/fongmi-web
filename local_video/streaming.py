"""HTTP Range 请求解析与分块流式响应。"""
import re
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
CHUNK_SIZE = 1024 * 1024


def parse_range(range_header: str | None, file_size: int) -> tuple[int, int] | None:
    """解析 Range 头，返回 (start, end)，无效时返回 None。

    支持：bytes=start-end / bytes=start- / bytes=-suffix
    """
    if not range_header or file_size <= 0:
        return None
    match = RANGE_RE.match(range_header.strip())
    if not match:
        return None
    start_s, end_s = match.groups()
    if not start_s and not end_s:
        return None
    if not start_s:
        suffix = int(end_s)
        if suffix <= 0:
            return None
        return (max(0, file_size - suffix), file_size - 1)
    start = int(start_s)
    if start >= file_size:
        return None
    end = int(end_s) if end_s else file_size - 1
    end = min(end, file_size - 1)
    if end < start:
        return None
    return (start, end)


def stream_video(file_path: Path, media_type: str, range_header: str | None):
    """按 Range 返回视频内容；无 Range 时返回 200 完整文件，有则 206 分块。"""
    file_size = file_path.stat().st_size
    if not range_header:
        return FileResponse(file_path, media_type=media_type, headers={"Accept-Ranges": "bytes"})

    rng = parse_range(range_header, file_size)
    if rng is None:
        raise HTTPException(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})
    start, end = rng
    length = end - start + 1

    def iter_chunks():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
    }
    from fastapi.responses import StreamingResponse

    return StreamingResponse(iter_chunks(), status_code=206, media_type=media_type, headers=headers)
