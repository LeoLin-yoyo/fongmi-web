"""抖音模块：分享链接解析 → 无水印直链（视频 / 图集）。

参考社区公开的 `_ROUTER_DATA` 解析思路（纯 HTTP，无需浏览器、无需签名），
用 Python/httpx 重新实现，与本项目其它来源（网盘/TG）共用下载引擎与播放代理。
"""
from .link import extract_url, parse_aweme_id
from .parser import DouyinError, parse_aweme, parse_page

__all__ = ["extract_url", "parse_aweme_id", "DouyinError", "parse_aweme", "parse_page"]
