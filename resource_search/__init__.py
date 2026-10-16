"""资源索引：把 TG 频道消息 / 网盘资源目录建成可搜索的本地索引。

聚合搜索接入点：spider/search.py 的 search_aggregated 返回 {merged, per_site}，
虚拟源只要产出同样的 vod 形态（带 _site_key）即可无缝并入 SearchPage。
"""
from .indexer import (
    clear_index,
    index_pan_folder,
    index_tg_chats,
    list_index_stats,
    search_resources,
)

__all__ = ["index_tg_chats", "index_pan_folder", "search_resources",
           "list_index_stats", "clear_index"]
