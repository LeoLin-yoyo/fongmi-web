"""共享测试夹具。"""
import subprocess

import pytest

from local_video.db import Database
from local_video.scanner import Scanner


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def scanner(db):
    return Scanner(db)


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory):
    """用 ffmpeg 生成 2 秒测试视频；ffmpeg 不可用时跳过。"""
    media_dir = tmp_path_factory.mktemp("media")
    video = media_dir / "sample.mp4"
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        str(video),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
    except (subprocess.SubprocessError, OSError):
        pytest.skip("ffmpeg 不可用，跳过")
    if result.returncode != 0 or not video.exists():
        pytest.skip(f"无法生成测试视频: {result.stderr.decode(errors='ignore')[-200:]}")
    return video
