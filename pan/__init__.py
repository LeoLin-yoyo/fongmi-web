"""网盘模块：分享链接解析 + 直链获取 + 转存（移植自 YunX 的接口协议，Python 重写）。"""
from .models import DownloadLink, PanError, ShareFile, ShareSession
from .link import detect_platform, parse_share_link, SUPPORTED_PLATFORMS

__all__ = [
    "DownloadLink", "PanError", "ShareFile", "ShareSession",
    "detect_platform", "parse_share_link", "SUPPORTED_PLATFORMS",
]
