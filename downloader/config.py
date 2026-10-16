"""下载引擎全局配置：下载目录（用户可在设置页自定义绝对路径）。"""
import os

from spider.proxy_config import get_config_value

DEFAULT_DOWNLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "downloads"
)


def get_download_dir() -> str:
    """当前下载目录：设置页自定义值优先，否则默认 data/downloads。"""
    d = get_config_value("download_dir").strip()
    return d or DEFAULT_DOWNLOAD_DIR
