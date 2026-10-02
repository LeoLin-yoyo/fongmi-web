"""本地视频模块运行时状态。"""
import logging

from .config import ensure_dirs
from .db import Database
from .scanner import Scanner

logger = logging.getLogger("local_video")


class AppState:
    def __init__(self):
        self.db: Database | None = None
        self.scanner: Scanner | None = None


app_state = AppState()


def init_local_video() -> None:
    """初始化本地视频模块：建库，由用户在设置页手动添加目录。"""
    ensure_dirs()
    app_state.db = Database()
    app_state.scanner = Scanner(app_state.db)
    logger.info("本地视频模块已启动，请在设置中添加媒体目录")
