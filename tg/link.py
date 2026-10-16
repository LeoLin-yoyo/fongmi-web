"""Telegram 链接解析与净化（移植 tdl-web sanitizeLink + resolve 口径）。

安全铁律：只接受 t.me 消息链接，且用硬编码 host 重新构造 URL——
交给 tdl 的字符串永远是本模块拼出来的，不是用户原始输入。
"""
import re
from urllib.parse import urlparse

# /name/msg[/topic] 或 /c/id/msg[/topic]
_PATH_RE = re.compile(r"^/(?:c/)?([A-Za-z0-9_]+|\d+)/(\d+)(?:/(\d+))?/?$")


class TgLink:
    def __init__(self, raw: str, peer: str, msg_id: int, topic_id: int = 0):
        self.raw = raw
        self.peer = peer
        self.msg_id = msg_id
        self.topic_id = topic_id

    def normalized(self) -> str:
        """规范化的 t.me URL（用于喂给 tdl）。"""
        if self.peer.isdigit():
            base = f"https://t.me/c/{self.peer}/{self.msg_id}"
        else:
            base = f"https://t.me/{self.peer}/{self.msg_id}"
        if self.topic_id:
            base += f"/{self.topic_id}"
        return base

    def to_dict(self) -> dict:
        return {"peer": self.peer, "msg_id": self.msg_id, "topic_id": self.topic_id,
                "url": self.normalized()}


def sanitize_link(raw: str) -> str | None:
    """校验并重建 t.me 链接；非法返回 None（不接受 user/pass/port，host 必须 t.me）。"""
    raw = (raw or "").strip()
    if not raw:
        return None
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    try:
        p = urlparse(raw)
    except ValueError:
        return None
    if p.hostname not in ("t.me", "telegram.me", "www.t.me"):
        return None
    if p.username or p.password or p.port:
        return None
    m = _PATH_RE.match(p.path)
    if not m:
        return None
    peer, msg_id, topic = m.group(1), int(m.group(2)), int(m.group(3) or 0)
    # 用硬编码 host 重新构造
    if peer.isdigit():
        out = f"https://t.me/c/{peer}/{msg_id}"
    else:
        out = f"https://t.me/{peer}/{msg_id}"
    if topic:
        out += f"/{topic}"
    return out


def parse_tg_link(raw: str) -> TgLink | None:
    """解析 t.me 链接为 TgLink；无法识别返回 None。"""
    normalized = sanitize_link(raw)
    if not normalized:
        return None
    p = urlparse(normalized)
    m = _PATH_RE.match(p.path)
    if not m:
        return None
    peer = m.group(1)
    return TgLink(raw=raw, peer=peer, msg_id=int(m.group(2)),
                  topic_id=int(m.group(3) or 0))


def extract_links(text: str) -> list[str]:
    """从任意文本中提取全部 t.me 链接（去重、保序）。"""
    seen = set()
    out = []
    for m in re.finditer(r"https?://(?:t\.me|telegram\.me)/[^\s\"'<>]+", text or ""):
        norm = sanitize_link(m.group(0))
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out
