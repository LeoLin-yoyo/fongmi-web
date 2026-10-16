"""Telegram 模块配置：tdl 路径、代理、下载目录、播放预取参数（存 data/config.json）。"""
from dataclasses import dataclass, asdict

from spider.proxy_config import get_config_value, set_config_value


@dataclass
class TgConfig:
    tdl_path: str = ""            # tdl 可执行文件路径（空=自动发现/PATH）
    ns: str = "default"           # tdl 命名空间
    proxy: str = ""               # 覆盖全局代理（空=用全局）
    download_dir: str = ""        # 空=用统一下载目录
    connections: int = 48         # 每文件并发连接
    file_concurrency: int = 3     # 同时下载文件数
    stream_connections: int = 24  # 播放预取连接数
    stream_window_mb: int = 96    # 预取窗口
    stream_cache_mb: int = 256    # 内存缓存上限
    include: str = ""             # 仅下载扩展名（逗号分隔）
    exclude: str = ""             # 排除扩展名


_FIELDS = list(TgConfig().__dict__.keys())


def get_config() -> TgConfig:
    cfg = TgConfig()
    for k in _FIELDS:
        raw = get_config_value(f"tg_{k}")
        if raw == "":
            continue
        cur = getattr(cfg, k)
        try:
            setattr(cfg, k, int(raw) if isinstance(cur, int) else raw)
        except (ValueError, TypeError):
            pass
    cfg.connections = max(1, min(cfg.connections, 64))
    cfg.file_concurrency = max(1, min(cfg.file_concurrency, 8))
    cfg.stream_connections = max(1, min(cfg.stream_connections, 128))
    cfg.stream_window_mb = max(8, min(cfg.stream_window_mb, 4096))
    cfg.stream_cache_mb = max(32, min(cfg.stream_cache_mb, 8192))
    return cfg


def save_config(patch: dict) -> TgConfig:
    for k, v in (patch or {}).items():
        if k in _FIELDS:
            set_config_value(f"tg_{k}", str(v))
    return get_config()
