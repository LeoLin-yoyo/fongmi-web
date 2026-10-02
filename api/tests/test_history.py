"""历史/收藏 API 测试"""
import pytest


class TestHistoryAPI:
    """GET /api/history, POST /api/history, PUT /api/history, GET /api/history/check"""

    def test_list_empty(self, client, setup_db):
        r = client.get("/api/history")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_add_and_list(self, client, setup_db):
        r = client.post("/api/history", json={
            "site_key": "site1", "vod_id": "vod1", "name": "测试影片",
            "pic": "", "episode": "第1集", "position": 30000, "duration": 120000,
        })
        assert r.status_code == 200
        assert r.json()["code"] == 0

        r = client.get("/api/history")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "测试影片"
        assert data["items"][0]["site_key"] == "site1"
        assert data["items"][0]["vod_id"] == "vod1"

    def test_add_duplicate_updates(self, client, setup_db):
        client.post("/api/history", json={
            "site_key": "s1", "vod_id": "v1", "name": "旧名",
            "episode": "第1集", "position": 0, "duration": 0,
        })
        client.post("/api/history", json={
            "site_key": "s1", "vod_id": "v1", "name": "新名",
            "episode": "第2集", "position": 50000, "duration": 120000,
        })
        r = client.get("/api/history")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "新名"
        assert data["items"][0]["episode"] == "第2集"

    def test_pagination(self, client, setup_db):
        for i in range(5):
            client.post("/api/history", json={
                "site_key": "s1", "vod_id": f"v{i}", "name": f"影片{i}",
                "episode": "", "position": 0, "duration": 0,
            })
        r = client.get("/api/history", params={"page": 1, "size": 2})
        data = r.json()
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["size"] == 2
        assert len(data["items"]) == 2

        r2 = client.get("/api/history", params={"page": 3, "size": 2})
        assert len(r2.json()["items"]) == 1

    def test_check_endpoint_found(self, client, setup_db):
        client.post("/api/history", json={
            "site_key": "s1", "vod_id": "v1", "name": "测试",
            "episode": "", "position": 30000, "duration": 120000,
        })
        r = client.get("/api/history/check", params={"site_key": "s1", "vod_id": "v1"})
        assert r.status_code == 200
        data = r.json()
        assert data["found"] is True
        assert data["position"] == 30000
        assert data["duration"] == 120000

    def test_check_endpoint_not_found(self, client, setup_db):
        r = client.get("/api/history/check", params={"site_key": "s1", "vod_id": "nonexistent"})
        assert r.status_code == 200
        assert r.json()["found"] is False

    def test_update_history(self, client, setup_db):
        client.post("/api/history", json={
            "site_key": "s1", "vod_id": "v1", "name": "测试",
            "episode": "", "position": 10000, "duration": 120000,
        })
        r = client.put("/api/history", json={
            "site_key": "s1", "vod_id": "v1", "position": 60000, "duration": 120000,
        })
        assert r.status_code == 200
        assert r.json()["code"] == 0

        r = client.get("/api/history/check", params={"site_key": "s1", "vod_id": "v1"})
        assert r.json()["position"] == 60000

    def test_delete_single(self, client, setup_db):
        client.post("/api/history", json={
            "site_key": "s1", "vod_id": "v1", "name": "测试",
            "episode": "", "position": 0, "duration": 0,
        })
        r = client.get("/api/history")
        item_id = r.json()["items"][0]["id"]

        r = client.delete(f"/api/history/{item_id}")
        assert r.status_code == 200

        r = client.get("/api/history")
        assert r.json()["total"] == 0

    def test_clear_all(self, client, setup_db):
        for i in range(3):
            client.post("/api/history", json={
                "site_key": "s1", "vod_id": f"v{i}", "name": f"影片{i}",
                "episode": "", "position": 0, "duration": 0,
            })
        r = client.delete("/api/history")
        assert r.status_code == 200
        assert client.get("/api/history").json()["total"] == 0

    def test_large_dataset(self, client, setup_db):
        """验证 200 条记录不分页截断"""
        for i in range(200):
            client.post("/api/history", json={
                "site_key": "s1", "vod_id": f"v{i}", "name": f"影片{i}",
                "episode": "", "position": i * 1000, "duration": 120000,
            })
        r = client.get("/api/history", params={"size": 200})
        data = r.json()
        assert data["total"] == 200
        assert len(data["items"]) == 200


class TestKeepAPI:
    """GET /api/keep, POST /api/keep, DELETE /api/keep, GET /api/keep/check"""

    def test_list_empty(self, client, setup_db):
        r = client.get("/api/keep")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_add_and_list(self, client, setup_db):
        r = client.post("/api/keep", json={
            "site_key": "s1", "vod_id": "v1", "name": "收藏影片", "pic": "",
        })
        assert r.status_code == 200
        assert r.json()["code"] == 0

        r = client.get("/api/keep")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "收藏影片"

    def test_duplicate_keep(self, client, setup_db):
        client.post("/api/keep", json={
            "site_key": "s1", "vod_id": "v1", "name": "测试",
        })
        r = client.post("/api/keep", json={
            "site_key": "s1", "vod_id": "v1", "name": "测试",
        })
        assert r.json()["msg"] == "already_keep"
        assert client.get("/api/keep").json()["total"] == 1

    def test_check_endpoint(self, client, setup_db):
        client.post("/api/keep", json={
            "site_key": "s1", "vod_id": "v1", "name": "测试",
        })
        r = client.get("/api/keep/check", params={"site_key": "s1", "vod_id": "v1"})
        assert r.json()["is_keep"] is True

        r = client.get("/api/keep/check", params={"site_key": "s1", "vod_id": "v2"})
        assert r.json()["is_keep"] is False

    def test_delete(self, client, setup_db):
        client.post("/api/keep", json={
            "site_key": "s1", "vod_id": "v1", "name": "测试",
        })
        item_id = client.get("/api/keep").json()["items"][0]["id"]
        r = client.delete(f"/api/keep/{item_id}")
        assert r.status_code == 200
        assert client.get("/api/keep").json()["total"] == 0

    def test_pagination(self, client, setup_db):
        for i in range(5):
            client.post("/api/keep", json={
                "site_key": "s1", "vod_id": f"v{i}", "name": f"收藏{i}",
            })
        r = client.get("/api/keep", params={"page": 1, "size": 2})
        data = r.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["page"] == 1