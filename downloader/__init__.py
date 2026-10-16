"""统一下载引擎：Range 分片并发 + 断点续传。

供 TG（tdl serve）与网盘直链共用，设计参考 YunX DownloadManager 与
tdl-web serve-dl 两套实测实现，关键约定：
- 数据文件写 <目标名>.part，预分配为完整大小（稀疏文件），任意 offset 写入合法
- sidecar <目标名>.part.meta.json 记录 {size, block, done:[块索引], partial:{块索引:已写字节}}
- 只有整块写满才标记 done；暂停保留块内偏移，续传从该偏移继续，一字节不浪费
- 完成时 os.replace(part → 最终名) 并删除 sidecar
"""
from .tasks import manager, init_downloader

__all__ = ["manager", "init_downloader"]
