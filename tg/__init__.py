"""Telegram 模块：tdl 包壳 —— 链接解析 / 登录 / 在线播放 / 下载。

设计参考 tdl-web（Node 包壳）的架构精华，用 Python asyncio 重写：
- 所有 tdl 调用经全局串行队列（tdl 的 bolt 数据库单写者）
- 下载走 `tdl dl --serve` + HTTP Range（tdl 自带下载器 O_TRUNC 无法续传）
- 在线播放加流式代理（serve 单连接 ~0.1MB/s，需多连接预取）
- 会话副本用逐字节文件复制（tdl migrate 有交互确认且可能留下截断文件）
"""
from .config import TgConfig, get_config, save_config
from .link import parse_tg_link, sanitize_link

__all__ = ["TgConfig", "get_config", "save_config", "parse_tg_link", "sanitize_link"]
