"""扫描器测试：递归发现、元数据入库、失效文件清理。"""
import os
from pathlib import Path

import pytest

VIDEO_EXT = {".mp4", ".mkv", ".webm"}


def _make_tree(tmp_path: Path) -> Path:
    root = tmp_path / "library"
    sub = root / "sub" / "deep"
    sub.mkdir(parents=True)
    return root, sub


def test_scan_recursive_discovery(sample_video, db, scanner, tmp_path):
    root, sub = _make_tree(tmp_path)
    import shutil
    v1 = sub / "movie1.mp4"
    shutil.copy2(sample_video, v1)
    (root / "notes.txt").write_text("not a video")
    (root / "movie2.mp4").write_bytes(sample_video.read_bytes())
    (root / "trailer.webm").write_bytes(b"\x1a\x45\xdf\xa3" * 10)

    scanner.scan_dir(str(root))

    rows = db.list_videos()
    assert len(rows) == 3
    paths = {r["path"] for r in rows}
    assert str(v1) in paths
    assert "notes.txt" not in paths


def test_scan_extracts_metadata(sample_video, db, scanner, tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    import shutil
    shutil.copy2(sample_video, root / "meta.mp4")

    scanner.scan_dir(str(root))

    row = db.get_video_by_path(str(root / "meta.mp4"))
    assert row is not None
    assert row["width"] == 320
    assert row["height"] == 240
    assert row["codec"] == "h264"
    assert row["duration"] is not None and 1.5 <= row["duration"] <= 3.0
    assert row["size"] > 0
    assert row["container"] == "mp4"


def test_scan_removes_deleted_files(sample_video, db, scanner, tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    import shutil
    v = root / "gone.mp4"
    shutil.copy2(sample_video, v)

    scanner.scan_dir(str(root))
    assert db.count_videos() == 1

    os.remove(v)
    scanner.scan_dir(str(root))
    assert db.count_videos() == 0


def test_scan_skips_missing_dir(db, scanner, tmp_path):
    scanner.scan_dir(str(tmp_path / "does-not-exist"))
    assert db.count_videos() == 0


def test_scan_rescans_updated_file(sample_video, db, scanner, tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    import shutil
    v = root / "changing.mp4"
    shutil.copy2(sample_video, v)
    scanner.scan_dir(str(root))
    first = db.get_video_by_path(str(v))
    assert first["mtime"] > 0

    os.utime(v, (first["mtime"] + 100, first["mtime"] + 100))
    scanner.scan_dir(str(root))
    second = db.get_video_by_path(str(v))
    assert second["mtime"] == pytest.approx(first["mtime"] + 100, abs=1.0)


def test_scan_status_progress(sample_video, db, scanner, tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    import shutil
    shutil.copy2(sample_video, root / "a.mp4")
    shutil.copy2(sample_video, root / "b.mp4")

    status = scanner.status
    assert status["scanning"] is False

    scanner.scan_dir(str(root))
    status = scanner.status
    assert status["scanning"] is False
    assert status["total"] == 2
    assert status["done"] == 2
