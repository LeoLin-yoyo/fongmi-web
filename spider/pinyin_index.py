"""本地片名拼音索引 — 支持拼音关键词容错搜索（如 "shenxia" → 神夏）

索引来源：搜索结果、首页/分类浏览中出现过的片名，持久化到 data/title_index.json。
当用户输入纯 ASCII 关键词时，用全拼/首字母匹配索引中的片名，回搜站点。
"""
import json
import os
import re
import threading
from collections import OrderedDict

from loguru import logger

try:
    from pypinyin import lazy_pinyin, Style
except ImportError:  # pragma: no cover - pinyin 容错为可选能力
    lazy_pinyin = None
    Style = None

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_INDEX_FILE = os.path.join(_DATA_DIR, "title_index.json")
_MAX_ENTRIES = 20000
_ASCII_RE = re.compile(r"^[a-zA-Z]+$")
_NON_WORD_RE = re.compile(r"[\W_]+", re.UNICODE)


def _is_ascii_keyword(kw: str) -> bool:
    return bool(kw) and bool(_ASCII_RE.match(kw))


def _normalize_title(name: str) -> str:
    """去掉标点/空格等，保留中英文与数字，用于匹配与去重"""
    return _NON_WORD_RE.sub("", name or "").lower()


class TitleIndex:
    def __init__(self):
        self._lock = threading.Lock()
        # title(normalized) -> {"name": 原始片名, "sites": {site_key, ...}, "py": 全拼, "initials": 首字母}
        self._entries = OrderedDict()
        self._loaded = False
        self._dirty = False

    def _load(self):
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._loaded = True
            try:
                if os.path.exists(_INDEX_FILE):
                    with open(_INDEX_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        self._entries[k] = v
            except Exception as e:
                logger.debug(f"title index load failed: {e}")

    def _save(self):
        if not self._dirty:
            return
        try:
            idx_dir = os.path.dirname(os.path.realpath(_INDEX_FILE))
            tmp = os.path.realpath(os.path.join(idx_dir, os.path.basename(_INDEX_FILE) + ".tmp"))
            if not tmp.startswith(idx_dir + os.sep):
                raise ValueError("index temp path escapes index dir")
            os.makedirs(idx_dir, exist_ok=True)
            from pathlib import Path
            Path(tmp).write_text(json.dumps(self._entries, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, _INDEX_FILE)
            self._dirty = False
        except Exception as e:
            logger.debug(f"title index save failed: {e}")

    @staticmethod
    def _pinyin_fields(name: str):
        if not lazy_pinyin:
            return "", ""
        py = lazy_pinyin(name, style=Style.NORMAL, errors="ignore")
        full = "".join(p.lower() for p in py if p)
        initials = "".join(
            p[0] for p in lazy_pinyin(name, style=Style.FIRST_LETTER, errors="ignore") if p
        ).lower()
        return full, initials

    def add_titles(self, names, site_key: str = ""):
        """登记一批片名；片名过多时淘汰最旧条目"""
        if not names:
            return
        self._load()
        added = False
        with self._lock:
            for raw in names:
                name = (raw or "").strip()
                if not name or len(name) > 100:
                    continue
                norm = _normalize_title(name)
                if not norm:
                    continue
                entry = self._entries.get(norm)
                if entry is None:
                    full, initials = self._pinyin_fields(name)
                    entry = {"name": name, "sites": [], "py": full, "initials": initials}
                    self._entries[norm] = entry
                    added = True
                if site_key and site_key not in entry["sites"]:
                    entry["sites"].append(site_key)
                    added = True
                self._entries.move_to_end(norm)
            while len(self._entries) > _MAX_ENTRIES:
                self._entries.popitem(last=False)
            if added:
                self._dirty = True
        if self._dirty:
            self._save()

    def find_by_keyword(self, keyword: str, limit: int = 5) -> list:
        """纯 ASCII 关键词 → 命中的中文片名（全拼前缀或首字母精确匹配）"""
        if not lazy_pinyin or not _is_ascii_keyword(keyword):
            return []
        self._load()
        kw = keyword.lower()
        hits = []
        with self._lock:
            for entry in self._entries.values():
                if entry["py"] == kw or entry["initials"] == kw:
                    hits.append((0, entry["name"]))
                elif entry["py"].startswith(kw) and len(entry["py"]) <= len(kw) + 4:
                    hits.append((1, entry["name"]))
                if len(hits) >= limit * 3:
                    break
        hits.sort(key=lambda x: x[0])
        # 按命中优先级去重，返回原始片名
        seen = set()
        result = []
        for _, name in hits:
            if name not in seen:
                seen.add(name)
                result.append(name)
            if len(result) >= limit:
                break
        return result

    def size(self) -> int:
        self._load()
        return len(self._entries)


title_index = TitleIndex()
