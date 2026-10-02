"""本地视频模块配置：数据目录、默认视频目录、媒体格式等。"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "local_video"
THUMB_DIR = DATA_DIR / "thumbs"
DB_PATH = DATA_DIR / "videos.db"

DEFAULT_VIDEO_DIRS = [r"F:\telegram"]

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi", ".flv",
    ".wmv", ".ts", ".mpeg", ".mpg", ".3gp", ".rmvb", ".rm", ".m2ts",
}

MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".flv": "video/x-flv",
    ".wmv": "video/x-ms-wmv",
    ".ts": "video/mp2t",
    ".m2ts": "video/mp2t",
    ".mpeg": "video/mpeg",
    ".mpg": "video/mpeg",
    ".3gp": "video/3gpp",
    ".rmvb": "video/vnd.rn-realvideo",
    ".rm": "video/vnd.rn-realvideo",
}


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
