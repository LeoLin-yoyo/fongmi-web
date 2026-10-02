"""搜索智能化单元测试（T3-1）：拼音索引 + 爬虫结果归一化"""
import os
import tempfile

import pytest

# 指向临时索引文件，避免污染真实 data/
_tmp_dir = tempfile.mkdtemp(prefix="pinyin_test_")
import spider.pinyin_index as pinyin_mod
pinyin_mod._INDEX_FILE = os.path.join(_tmp_dir, "title_index.json")
pinyin_mod.title_index = pinyin_mod.TitleIndex()

from spider.pinyin_index import title_index, _is_ascii_keyword  # noqa: E402
from spider.search import _normalize_spider_result  # noqa: E402


class TestPinyinIndex:
    def test_ascii_check(self):
        assert _is_ascii_keyword("shenxia")
        assert _is_ascii_keyword("stxlk")
        assert not _is_ascii_keyword("神夏")
        assert not _is_ascii_keyword("")
        assert not _is_ascii_keyword("shen xia")
        assert not _is_ascii_keyword("shen123")

    def test_full_pinyin_match(self):
        title_index.add_titles(["神夏", "狂飙"], "site_a")
        assert "神夏" in title_index.find_by_keyword("shenxia")
        assert title_index.find_by_keyword("kuangbiao") == ["狂飙"]

    def test_initials_match(self):
        title_index.add_titles(["神探夏洛克"], "site_a")
        assert title_index.find_by_keyword("stxlk") == ["神探夏洛克"]

    def test_no_match(self):
        assert title_index.find_by_keyword("zzzzzz") == []

    def test_chinese_keyword_not_matched(self):
        # 中文关键词不走拼音通道
        assert title_index.find_by_keyword("神夏") == []

    def test_persist_and_reload(self):
        idx = pinyin_mod.TitleIndex()
        idx.add_titles(["测试持久化影片"], "site_p")
        # 新实例从文件恢复
        idx2 = pinyin_mod.TitleIndex()
        assert "测试持久化影片" in idx2.find_by_keyword("cscjhyp")


class TestSpiderResultNormalize:
    def test_dict_list_form(self):
        raw = {"list": [{"vod_id": "1", "vod_name": "神夏"}]}
        items = _normalize_spider_result(raw, "s1", "Site1")
        assert len(items) == 1
        assert items[0]["_site_key"] == "s1"
        assert items[0]["_site_name"] == "Site1"

    def test_plain_list_form(self):
        items = _normalize_spider_result([{"vod_id": "2", "vod_name": "X"}], "s1", "Site1")
        assert len(items) == 1

    def test_filters_ads_and_empty(self):
        raw = {"list": [
            {"vod_name": ""},
            {"vod_name": "✈飞机"},
            {"vod_name": "点击关注"},
            {"vod_id": "3", "vod_name": "好片"},
        ]}
        items = _normalize_spider_result(raw, "s1", "Site1")
        assert [i["vod_name"] for i in items] == ["好片"]

    def test_none_and_garbage(self):
        assert _normalize_spider_result(None, "s1", "S") == []
        assert _normalize_spider_result({"list": ["notdict", 42]}, "s1", "S") == []
