"""埋点基线 API 测试（T0-1）"""
import os
import tempfile

import pytest

# 指向临时目录，避免污染真实 data/metrics
_tmp_metrics = os.path.join(tempfile.mkdtemp(prefix="metrics_test_"), "metrics")
import api.metrics as metrics_mod
metrics_mod._METRICS_DIR = _tmp_metrics


class TestMetricsAPI:
    def test_report_and_summary(self, client):
        r = client.post("/api/metrics/event", json={
            "type": "ttff", "sid": "s1", "data": {"ms": 1500, "resolution": "720p"},
        })
        assert r.status_code == 200
        assert r.json()["code"] == 0

        r = client.post("/api/metrics/event", json={
            "type": "ttff", "sid": "s2", "data": {"ms": 2500},
        })
        assert r.status_code == 200

        r = client.post("/api/metrics/event", json={
            "type": "session", "sid": "s1",
            "data": {"play_ms": 60000, "rebuffer_count": 2, "rebuffer_ms": 800, "completed": False},
        })
        assert r.status_code == 200

        r = client.post("/api/metrics/event", json={
            "type": "complete", "sid": "s1", "data": {"duration_ms": 90000},
        })
        assert r.status_code == 200

        r = client.post("/api/metrics/event", json={
            "type": "nav", "sid": "s1", "data": {"from": "/", "to": "/play"},
        })
        assert r.status_code == 200

        summary = client.get("/api/metrics/summary").json()
        assert summary["ttff"]["count"] == 2
        assert summary["ttff"]["p50_ms"] == 2000
        assert summary["playback"]["sessions"] == 1
        assert summary["playback"]["rebuffer_count"] == 2
        assert summary["playback"]["completes"] == 1
        assert summary["nav"]["home_to_play_samples"] == 1
        assert summary["nav"]["steps_p95"] == 1

    def test_invalid_type_ignored(self, client):
        r = client.post("/api/metrics/event", json={"type": "hack", "data": {}})
        assert r.status_code == 200
        assert r.json().get("ignored") is True

    def test_export_writes_baseline(self, client):
        client.post("/api/metrics/event", json={"type": "ttff", "sid": "s1", "data": {"ms": 1800}})
        r = client.get("/api/metrics/export")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert os.path.basename(body["file"]).startswith("baseline-")
        assert os.path.exists(body["file"])
        assert body["summary"]["ttff"]["count"] >= 1

    def test_raw_filter(self, client):
        client.post("/api/metrics/event", json={"type": "error", "sid": "s1", "data": {"message": "x"}})
        r = client.get("/api/metrics/raw?type=error")
        assert r.status_code == 200
        assert all(ev["type"] == "error" for ev in r.json()["events"])

    def test_raw_rejects_bad_type(self, client):
        r = client.get("/api/metrics/raw?type=bad%20type!")
        assert r.status_code == 200
        assert r.json()["events"] == []
