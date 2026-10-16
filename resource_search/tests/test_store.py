"""资源索引测试：片名清洗、写入去重、检索、虚拟源形态。"""
import asyncio

import pytest

from resource_search import store
from resource_search.store import normalize_name, is_video


def test_normalize_name():
    assert normalize_name("复仇者联盟.2012.1080p.BluRay.x264.mp4") == "复仇者联盟 2012"
    assert normalize_name("【电影】星际穿越[2160p].mkv") == "电影 星际穿越"
    assert normalize_name("Breaking.Bad.S01E01.720p.HDTV.mkv").startswith("Breaking Bad")


def test_is_video():
    assert is_video("a.mp4") and is_video("a.MKV") and is_video("a.rmvb")
    assert not is_video("a.pdf") and not is_video("a.zip")


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    from model.database import Base, engine

    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(_create())
    yield


def test_upsert_and_query():
    async def go():
        await store.clear()
        added = await store.upsert_entries([
            {"kind": "tg", "site_key": "tg:@test", "site_name": "TG·@test",
             "name": "复仇者联盟.2012.1080p.mp4", "size": 2 * 1024 ** 3,
             "payload": {"sid": "x", "href": "1/1"}, "source_ref": "tg:@test:1/1"},
            {"kind": "pan", "site_key": "pan:quark", "site_name": "网盘·quark",
             "name": "星际穿越.2160p.mkv", "size": 5 * 1024 ** 3,
             "payload": {"platform": "quark", "share_id": "abc", "fid": "f1"},
             "source_ref": "pan:quark:abc:f1"},
        ])
        assert added == 2
        # 去重：同 source_ref 再写不新增
        added2 = await store.upsert_entries([
            {"kind": "tg", "site_key": "tg:@test", "name": "复仇者联盟.2012.1080p.mp4",
             "source_ref": "tg:@test:1/1", "payload": {}},
        ])
        assert added2 == 0
        # 检索：清洗后匹配
        res = await store.query("复仇者")
        assert len(res) == 1
        assert res[0]["_site_key"] == "tg:@test"
        assert res[0]["_kind"] == "tg"
        # 中文关键词命中
        assert len(await store.query("星际穿越")) == 1
        # 无结果
        assert await store.query("不存在的片名xyz") == []
    asyncio.run(go())


def test_search_resources_shape():
    async def go():
        await store.clear()
        await store.upsert_entries([
            {"kind": "tg", "site_key": "tg:@c", "site_name": "TG·@c",
             "name": "测试电影.2023.mp4", "size": 100, "payload": {"sid": "s", "href": "1/2"},
             "source_ref": "tg:@c:1/2"},
        ])
        from resource_search.indexer import search_resources
        out = await search_resources("测试电影")
        assert "merged" in out and "per_site" in out
        assert out["per_site"]["tg:@c"]["results"]
        # vod 形态字段
        item = out["merged"][0]
        for k in ("vod_id", "vod_name", "_site_key", "_site_name", "_kind"):
            assert k in item
    asyncio.run(go())


def test_stats_and_clear():
    async def go():
        await store.clear()
        await store.upsert_entries([
            {"kind": "tg", "site_key": "tg:@a", "site_name": "A", "name": "x.mp4",
             "source_ref": "tg:@a:1", "payload": {}},
            {"kind": "pan", "site_key": "pan:uc", "site_name": "B", "name": "y.mp4",
             "source_ref": "pan:uc:1", "payload": {}},
        ])
        st = await store.stats()
        assert {s["site_key"] for s in st} == {"tg:@a", "pan:uc"}
        n = await store.clear("tg")
        assert n == 1
        st2 = await store.stats()
        assert {s["site_key"] for s in st2} == {"pan:uc"}
        await store.clear()
    asyncio.run(go())
