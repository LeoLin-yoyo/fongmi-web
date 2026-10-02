"""直播 EPG API 测试"""
import pytest


class TestLiveEPG:

    def test_epg_without_config_returns_empty(self, client, setup_db):
        """没有配置时 EPG 返回空列表"""
        r = client.get("/api/live/epg", params={"source_idx": 0})
        assert r.status_code == 200
        data = r.json()
        assert data == {"epg": []}

    def test_epg_with_invalid_index_returns_empty(self, client, setup_db):
        """超出范围的索引返回空列表"""
        r = client.get("/api/live/epg", params={"source_idx": 999})
        assert r.status_code == 200
        assert r.json() == {"epg": []}

    def test_groups_without_config_returns_empty(self, client, setup_db):
        r = client.get("/api/live/groups")
        assert r.status_code == 200
        assert r.json() == []

    def test_channels_without_config_returns_empty(self, client, setup_db):
        r = client.get("/api/live/channels", params={"source_idx": 0})
        assert r.status_code == 200
        assert r.json() == []