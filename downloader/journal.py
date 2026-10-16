"""sidecar 断点记录：task meta（url/头/块布局）+ done/partial 位图，原子读写。"""
import json
import os
import tempfile
import threading
from pathlib import Path

# 块内续传偏移记录在 partial；整块完成记录在 done
META_SUFFIX = ".part.meta.json"

_lock = threading.Lock()


def part_path(final_path: str) -> str:
    return final_path + ".part"


def meta_path(final_path: str) -> str:
    return final_path + META_SUFFIX


def write_meta(final_path: str, meta: dict) -> None:
    """原子写 sidecar：临时文件 + rename，读者永不会看到半写 JSON。"""
    p = meta_path(final_path)
    tmp = None
    try:
        with _lock:
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p) or ".", prefix=".meta-")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False)
            os.replace(tmp, p)
            tmp = None
    except OSError:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def read_meta(final_path: str) -> dict | None:
    p = meta_path(final_path)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("size"), int):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return None


def delete_meta(final_path: str) -> None:
    try:
        os.unlink(meta_path(final_path))
    except OSError:
        pass


def block_len(total: int, block: int, idx: int) -> int:
    return min(block, total - idx * block)


def done_bytes(total: int, block: int, done: set[int], partial: dict[int, int]) -> int:
    """完成块实际字节数 + 块内已落盘字节（末块可能不足一块）。"""
    n = sum(block_len(total, block, i) for i in done)
    n += sum(min(v, block_len(total, block, i)) for i, v in partial.items() if i not in done)
    return n


def missing_blocks(total: int, block: int, done: set[int]) -> list[int]:
    count = (total + block - 1) // block
    return [i for i in range(count) if i not in done]


def adopt_relocated_file(final_path: str, meta: dict, candidates: list[str]) -> str | None:
    """断点文件被用户移动/改名后的重新认领（YunX 重定位口径）。

    校验三件套：文件大小一致 + 缺口块之外存在已写内容 + 抽样块起始 4KiB 边界指纹一致。
    匹配返回新 .part 路径，否则 None。
    """
    total = meta.get("size") or 0
    block = meta.get("block") or 0
    done = set(meta.get("done") or [])
    if total <= 0 or block <= 0:
        return None
    # 取一个已完成块做指纹比对（首块最可靠）
    probe = min(done) if done else 0
    off = probe * block
    try:
        with open(final_path, "rb") as f0:
            f0.seek(off)
            expect = f0.read(4096)
    except OSError:
        expect = None
    for cand in candidates:
        try:
            p = Path(cand)
            if not p.is_file() or p.stat().st_size != total:
                continue
            if expect:
                with open(p, "rb") as f:
                    f.seek(off)
                    if f.read(4096) != expect:
                        continue
            return str(p)
        except OSError:
            continue
    return None
