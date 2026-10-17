"""抖音分享链接识别（移植社区公开的链接形态规则）。

支持的形态：
- 短链：https://v.douyin.com/xxxx/
- 分享页：https://www.iesdouyin.com/share/{video|slides|note}/<id>
- 网页：https://(www.|m.)douyin.com/{video|note|slides}/<id>
- 网页短形态：https://www.douyin.com/<id>
"""
import re

URL_RE = re.compile(
    r"https?://(?:v\.douyin\.com/\S+"
    r"|(?:www\.)?iesdouyin\.com/share/(?:video|slides|note)/\d+"
    r"|(?:www\.|m\.)?douyin\.com/(?:video|note|slides)/\d+"
    r"|www\.douyin\.com/\d+)"
)
ID_RE = re.compile(r"/(?:video|slides|note)/(\d+)")
# 裸 ID 形态：https://www.douyin.com/<19位数字>
BARE_ID_RE = re.compile(r"^https?://(?:www\.)?douyin\.com/(\d{15,25})/?$")
ANY_HTTP_RE = re.compile(r"https?://[^\s<>\"']+", re.I)

# 链接尾部常见中文标点，提取后需要剥掉
_TRAILING = "，。；）)]}>\u3000"


def extract_url(text: str) -> str | None:
    """从任意文本（分享口令/文案）中提取抖音链接。"""
    if not text:
        return None
    m = URL_RE.search(text)
    if m:
        return m.group(0).rstrip("/")
    m = ANY_HTTP_RE.search(text)
    if m:
        return m.group(0).rstrip(_TRAILING).rstrip("/")
    return None


def parse_aweme_id(url: str) -> str | None:
    """从已知形态的链接里直接取 aweme_id（短链需先跟随重定向）。"""
    url = (url or "").strip()
    m = ID_RE.search(url)
    if m:
        return m.group(1)
    m = BARE_ID_RE.match(url)
    return m.group(1) if m else None


def extract_aweme_id_from_redirect(final_url: str) -> str | None:
    """短链跟随重定向后，从最终 URL 里取 aweme_id。"""
    return parse_aweme_id(final_url or "")
