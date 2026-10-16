"""分享链接识别：平台判定 + 分享短码 + 提取码提取（移植 YunX ShareLinkParser 规则）。"""
import re
from urllib.parse import urlparse, parse_qs

from .models import ShareSession

URL_RE = re.compile(r"https?://[^\s]+")
TRIM_CHARS = "。,;;)]}\"'"

PWD_IN_URL_RE = re.compile(r"[?&]pwd=([A-Za-z0-9]+)")
PWD_IN_115_RE = re.compile(r"[?&]password=([A-Za-z0-9]+)")
PWD_IN_LANZOU_RE = re.compile(r"[?&](?:pwd|pass|passcode|password)=([A-Za-z0-9]+)")
PWD_IN_TEXT_RE = re.compile(r"(?:提取码|访问码|密码)[：:]\s*([A-Za-z0-9]{4,8})")

PLATFORMS = {
    "quark": re.compile(r"pan\.quark\.cn/s/([A-Za-z0-9]+)", re.I),
    "uc": re.compile(r"drive\.uc\.cn/s/([A-Za-z0-9]+)", re.I),
    "xunlei": re.compile(r"pan\.xunlei\.com/s/([A-Za-z0-9_-]+)", re.I),
    "baidu": re.compile(r"pan\.baidu\.com/s/(1[A-Za-z0-9_-]+)", re.I),
    "c139": re.compile(r"yun\.139\.com/shareweb/.*?/w/i/([A-Za-z0-9_-]+)", re.I),
    "pan123": re.compile(r"123(?:865|pan)\.(?:com|cn)/s/([A-Za-z0-9]+-[A-Za-z0-9]+)", re.I),
    "pan123_sub": re.compile(r"share\.123pan\.cn/123pan/([A-Za-z0-9-]+)", re.I),
    "pan123_srr": re.compile(r"api/srr\?sk=([A-Za-z0-9-]+)", re.I),
    "pan115": re.compile(r"115(?:cdn|rc)?\.com/s/(sw[A-Za-z0-9]+)", re.I),
    "pan115_cmd": re.compile(r"115(?:cdn|rc)?\.com/(sw[A-Za-z0-9]{8,})-([A-Za-z0-9]{4,8})"),
    "guangya": re.compile(r"guangyapan\.com/s/([A-Za-z0-9_-]+)", re.I),
    "ilanzou": re.compile(r"(?:^|[/.])ilanzou\.(?:com|net|org|cn)/s/([A-Za-z0-9_-]+)", re.I),
    "lanzou": re.compile(r"(?:^|[/.])(?:lanzou[a-z0-9-]*|lan[zs]o[ux])\.(?:com|net|org|cn)/([A-Za-z0-9]+)", re.I),
}

SUPPORTED_PLATFORMS = ["quark", "uc", "xunlei", "baidu", "c139", "pan123", "pan115", "guangya", "lanzou", "ilanzou"]

_LABEL = {
    "quark": "夸克网盘", "uc": "UC网盘", "xunlei": "迅雷网盘", "baidu": "百度网盘",
    "c139": "139网盘", "pan123": "123云盘", "pan115": "115网盘", "guangya": "光鸭云盘",
    "lanzou": "蓝奏云", "ilanzou": "蓝奏云优享版",
}


def platform_label(platform: str) -> str:
    return _LABEL.get(platform, platform)


def detect_platform(text: str) -> str:
    """识别链接归属平台（返回规范键，识别不出返回空串）。"""
    for key in SUPPORTED_PLATFORMS:
        if PLATFORMS[key].search(text or ""):
            return key
    return ""


def _extract_pwd(url: str, text: str, platform: str) -> str:
    if platform == "pan115":
        m = PWD_IN_115_RE.search(url)
    elif platform in ("lanzou", "ilanzou"):
        m = PWD_IN_LANZOU_RE.search(url)
    else:
        m = PWD_IN_URL_RE.search(url)
    if m:
        return m.group(1)
    m = PWD_IN_TEXT_RE.search(text)
    if m:
        return m.group(1)
    return ""


def parse_share_link(text: str) -> ShareSession | None:
    """粘贴文本 → ShareSession（platform/share_id/passcode），无法识别返回 None。"""
    text = (text or "").strip()
    m = URL_RE.search(text)
    if not m:
        return None
    url = m.group(0).rstrip(TRIM_CHARS)

    def _make(key: str, sid: str, pwd: str = "") -> ShareSession:
        if key == "baidu":
            sid = sid.removeprefix("1")  # 百度 surl 不含开头的 1
        return ShareSession(platform=key, share_id=sid, passcode=pwd or _extract_pwd(url, text, key))

    for key in ("quark", "uc", "xunlei", "baidu", "c139"):
        mm = PLATFORMS[key].search(url)
        if mm:
            return _make(key, mm.group(1))

    for key in ("pan123", "pan123_sub", "pan123_srr"):
        mm = PLATFORMS[key].search(url)
        if mm:
            return _make("pan123", mm.group(1))

    mm = PLATFORMS["pan115"].search(url)
    if mm:
        return _make("pan115", mm.group(1))
    mm = PLATFORMS["pan115_cmd"].search(url)
    if mm:  # 115 口令形态：/swxxxxx-nnnn/ —— 后段即提取码
        return ShareSession(platform="pan115", share_id=mm.group(1), passcode=mm.group(2))

    mm = PLATFORMS["guangya"].search(url)
    if mm:
        return _make("guangya", mm.group(1))

    # ilanzou 先于 lanzou 判断，避免混淆
    for key in ("ilanzou", "lanzou"):
        mm = PLATFORMS[key].search(url)
        if mm:
            return _make(key, mm.group(1))

    return None


def extract_query_passcode(url: str) -> str:
    """从 URL query 里拿提取码（各平台参数名不一）。"""
    try:
        qs = parse_qs(urlparse(url).query)
        for k in ("pwd", "pass", "passcode", "password"):
            if k in qs and qs[k]:
                return qs[k][0]
    except ValueError:
        pass
    return ""
