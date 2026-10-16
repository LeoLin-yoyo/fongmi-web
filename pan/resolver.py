"""解析编排与直链签发：分享会话缓存 + 文件树浏览 + 播放令牌。

签发口径（继承 tdl-web 安全设计）：download 接口只返回服务端签发的 token，
播放/下载字节流都经 token 换回「直链 + 绑定请求头」，外部无法借本接口请求任意 URL。
"""
import time
from collections import OrderedDict

from . import accounts
from .models import DownloadLink, PanError, ShareFile, ShareSession

# 分享会话缓存：(platform, share_id, passcode) → (session, 过期时间)
_SESSIONS: OrderedDict[str, tuple[ShareSession, float]] = OrderedDict()
_SESSION_TTL = 30 * 60
# 直链签发：token → (link, 过期时间)。直链本身约 3 小时有效（x-ttl=10800），这里取 2 小时。
_LINKS: OrderedDict[str, tuple[DownloadLink, float]] = OrderedDict()
_LINK_TTL = 2 * 3600
_LINK_MAX = 200


def _put(store: OrderedDict, key: str, value) -> None:
    store[key] = value
    while len(store) > _LINK_MAX:
        store.popitem(last=False)


def _session_key(platform: str, share_id: str, passcode: str) -> str:
    return f"{platform}:{share_id}:{passcode}"


async def resolve_share(platform: str, share_id: str, passcode: str = "",
                        force: bool = False) -> tuple[ShareSession, object]:
    """分享短码 → 会话（stoken）+ 平台客户端。会话缓存复用，避免重复取 token 触发频控。"""
    client = await accounts.get_client(platform)
    if client is None:
        raise PanError(f"暂不支持的平台: {platform}")
    key = _session_key(platform, share_id, passcode)
    now = time.monotonic()
    if not force and key in _SESSIONS:
        sess, exp = _SESSIONS[key]
        if exp > now:
            _SESSIONS.move_to_end(key)
            return sess, client
    sess = await client.create_session(share_id, passcode)
    _SESSIONS[key] = (sess, now + _SESSION_TTL)
    return sess, client


async def list_dir(platform: str, share_id: str, passcode: str,
                   pdir_fid: str = "0") -> list[ShareFile]:
    """列一个目录（自动翻页，封顶 100 页防异常死循环——YunX 同款）。"""
    sess, client = await resolve_share(platform, share_id, passcode)
    page_size = 100 if platform == "quark" else 50
    files: list[ShareFile] = []
    page = 1
    while page <= 100:
        batch = await client.list_share_files(sess, pdir_fid=pdir_fid, page=page, size=page_size)
        files.extend(batch)
        if len(batch) < page_size:
            break
        page += 1
    return files


async def find_by_fid(platform: str, share_id: str, passcode: str, fid: str,
                      max_depth: int = 6) -> ShareFile | None:
    """在分享目录树中按 fid 定位单文件（BFS，深度限制防失控）。"""
    sess, client = await resolve_share(platform, share_id, passcode)
    frontier = ["0"]
    depth = 0
    while frontier and depth <= max_depth:
        depth += 1
        nxt: list[str] = []
        for fid_level in frontier:
            try:
                files = await list_dir(platform, share_id, passcode, fid_level)
            except PanError:
                continue
            for f in files:
                if f.fid == fid:
                    return f
                if f.isdir:
                    nxt.append(f.fid)
        frontier = nxt
    return None


async def issue_link(platform: str, share_id: str, passcode: str,
                     file: ShareFile) -> DownloadLink:
    """取直链并签发 token。未登录且平台支持游客时走游客链路。"""
    sess, client = await resolve_share(platform, share_id, passcode)
    use_guest = not client.cookie and getattr(client, "GUEST_SUPPORTED", False)
    limit = getattr(client, "GUEST_MAX_BYTES", 0)
    if use_guest and limit and file.fsize > limit:
        raise PanError(
            f"{client.label}游客播放限约 {limit // 1024 // 1024}MB，"
            f"该文件 {file.fsize // 1024 // 1024}MB 超限，请在「设置 → 网盘账号」登录")
    if use_guest:
        link = await client.get_guest_download_link(sess, file)
    else:
        link = await client.get_share_download_link(sess, file)
    if not link.url:
        raise PanError("未获取到下载直链")
    import secrets
    token = secrets.token_urlsafe(9)
    link.token = token
    link.platform = platform
    link.share_id = share_id
    _put(_LINKS, token, (link, time.monotonic() + _LINK_TTL))
    return link


def take_link(token: str) -> DownloadLink | None:
    """换取签发直链；过期自动清除。"""
    entry = _LINKS.get(token)
    if not entry:
        return None
    link, exp = entry
    if exp < time.monotonic():
        _LINKS.pop(token, None)
        return None
    return link


def guest_notice(client) -> str:
    if not getattr(client, "GUEST_SUPPORTED", False):
        return "未登录：可查看文件列表，播放/下载需先登录账号"
    limit = getattr(client, "GUEST_MAX_BYTES", 0)
    if limit:
        return f"未登录：可直接播放约 {limit // 1024 // 1024}MB 以内的文件，更大文件请先登录"
    return "未登录：本平台游客可直接解析播放"
