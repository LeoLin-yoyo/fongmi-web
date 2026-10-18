"""迅雷网盘客户端（移植 YunX XunleiApi 协议，Python/httpx 重写）。

链路：share?share_id 列目录（列表匿名可用）→ files/<id> 取直链；
取链/转存需 access_token（Bearer）。游客可选不写 Authorization（写了反而被判 unauthenticated）。
"""
import hashlib
import secrets
import string
from urllib.parse import quote

from ..base import PanClient
from ..models import DownloadLink, PanError, ShareFile, ShareSession

PAN_BASE = "https://api-pan.xunlei.com"
WEB_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
CLIENT_VERSION = "8.31.0.9726"

SHARE_OPEN = f"{PAN_BASE}/drive/v1/share"
SHARE_DETAIL = f"{PAN_BASE}/drive/v1/share/detail"
SHARE_RESTORE = f"{PAN_BASE}/drive/v1/share/restore"
TASK_URL = f"{PAN_BASE}/drive/v1/tasks"
FILES_URL = f"{PAN_BASE}/drive/v1/files"


class XunleiClient(PanClient):
    platform = "xunlei"
    label = "迅雷网盘"
    REQUIRED_COOKIES = ()          # 迅雷用 access_token，不用 Cookie
    GUEST_SUPPORTED = True         # 列表匿名；取直链需 token（游客取链会由服务端拒绝）
    GUEST_MAX_BYTES = 0

    def __init__(self, cookie="", cookie_sink=None):
        super().__init__(cookie, cookie_sink)
        # 账号以 JSON 形式存于 cookie 字段：{"access_token": "...", "refresh_token": "...", "device_id": "..."}
        self.access_token = ""
        self.refresh_token = ""
        self.device_id = ""
        self.captcha_token = ""
        self._parse_credential(cookie)

    def _parse_credential(self, raw: str):
        if raw:
            import json
            try:
                data = json.loads(raw)
                self.access_token = data.get("access_token") or data.get("accessToken") or ""
                self.refresh_token = data.get("refresh_token") or data.get("refreshToken") or ""
                self.device_id = data.get("device_id") or ""
                self.captcha_token = data.get("captcha_token") or ""
            except (ValueError, TypeError):
                # 也接受纯 access_token 字符串
                self.access_token = raw.strip()
        # device_id 始终存在（游客链路也需要 X-Device-Id 头）
        if not self.device_id:
            self.device_id = hashlib.md5(str(secrets.randbelow(10**12)).encode()).hexdigest()[:32]

    @classmethod
    def is_valid_cookie(cls, cookie: str) -> bool:
        if not cookie:
            return False
        try:
            import json
            d = json.loads(cookie)
            return bool(d.get("access_token") or d.get("accessToken"))
        except (ValueError, TypeError):
            return len(cookie.strip()) > 20

    def api_user_agent(self) -> str:
        return WEB_UA

    def _pan_headers(self) -> dict:
        h = {
            "User-Agent": WEB_UA,
            "X-Device-Id": self.device_id,
            "X-Client-Version": CLIENT_VERSION,
            "Origin": "https://pan.xunlei.com",
            "Referer": "https://pan.xunlei.com/",
            "Content-Type": "application/json",
        }
        # 游客不写 Authorization（带失效 Bearer 反被判 unauthenticated）
        if self.access_token:
            h["Authorization"] = f"Bearer {self.access_token}"
        if self.captcha_token:
            h["X-Captcha-Token"] = self.captcha_token
        return h

    async def _pan_get(self, url: str) -> dict:
        self._ensure_proxy()
        resp = await self._client.get(url, headers=self._pan_headers())
        return self._check(resp)

    async def _pan_post(self, url: str, body: dict) -> dict:
        self._ensure_proxy()
        resp = await self._client.post(url, json=body, headers=self._pan_headers())
        return self._check(resp)

    def _check(self, resp) -> dict:
        try:
            data = resp.json()
        except Exception:
            raise PanError(f"响应解析失败（HTTP {resp.status_code}）")
        if resp.status_code == 401 or data.get("error") == "unauthenticated":
            raise PanError("迅雷登录态已失效，请重新登录", 401)
        if data.get("error"):
            if data.get("error") == "captcha_invalid":
                raise PanError("迅雷验证码无效，请重试")
            raise PanError(data.get("error_description") or data.get("message") or data.get("error"))
        return data

    # ---------- 账号 ----------
    async def fetch_nickname(self) -> str:
        try:
            data = await self._pan_get(f"{PAN_BASE}/drive/v1/about")
            return ""  # about 不返回昵称
        except PanError:
            raise

    async def refresh_session(self):
        pass  # 迅雷刷新 token 需完整 OAuth 流程，此处仅靠 access_token 有效期

    # ---------- 分享解析 ----------
    async def create_session(self, share_id: str, passcode: str = "") -> ShareSession:
        return ShareSession(platform=self.platform, share_id=share_id,
                            passcode=passcode or "")

    async def list_share_files(self, session: ShareSession, pdir_fid: str = "",
                               page: int = 1, size: int = 100) -> list[ShareFile]:
        # 根目录用 share 端点，子目录用 share/detail
        if not pdir_fid:
            url = (f"{SHARE_OPEN}?share_id={session.share_id}"
                   f"&pass_code={quote(session.passcode or '', safe='')}"
                   f"&limit={size}&thumbnail_size=SIZE_SMALL")
        else:
            token = session.raw.get("pass_code_token") or ""
            url = (f"{SHARE_DETAIL}?share_id={session.share_id}&parent_id={pdir_fid}"
                   f"&pass_code_token={quote(token, safe='')}&limit={size}&thumbnail_size=SIZE_SMALL")
        data = await self._pan_get(url)
        d = data.get("data") or data
        status = d.get("share_status")
        if status == "PASS_CODE_EMPTY":
            raise PanError("请输入提取码")
        if status == "PASS_CODE_ERROR":
            raise PanError("提取码错误")
        if status == "PASS_CODE_NEED":
            raise PanError("该分享需要提取码")
        if not session.raw.get("pass_code_token"):
            session.raw["pass_code_token"] = d.get("pass_code_token") or ""
            session.title = d.get("title") or ""
        return self._parse_files(d.get("files") or [])

    @staticmethod
    def _parse_files(files: list) -> list[ShareFile]:
        out = []
        for f in files:
            out.append(ShareFile(
                fid=str(f.get("id") or ""),
                fname=str(f.get("name") or ""),
                fsize=int(f.get("size") or 0),
                isdir=(f.get("kind") == "drive#folder"),
                pdir_fid=str(f.get("parent_id") or ""),
                updated_at=str(f.get("modified_time") or ""),
            ))
        return out

    async def get_share_download_link(self, session: ShareSession, file: ShareFile) -> DownloadLink:
        if not self.access_token:
            raise PanError("下载需要先登录迅雷网盘（设置 → 网盘账号）")
        url = (f"{FILES_URL}/{file.fid}?_magic=2021&usage=PLAY"
               f"&thumbnail_size=SIZE_LARGE&with=hdr10&with=subtitle_files&with=task&with=public_share_tag")
        data = await self._pan_get(url)
        d = data.get("data") or data
        links = d.get("links") or {}
        octet = links.get("application/octet-stream") or {}
        direct = octet.get("url") or d.get("web_content_link") or ""
        if not direct:
            raise PanError("未返回下载链接")
        return DownloadLink(
            fid=str(d.get("id") or file.fid), filename=str(d.get("name") or file.fname),
            url=direct, size=int(d.get("size") or file.fsize),
            headers={"User-Agent": WEB_UA, "Referer": "https://pan.xunlei.com/",
                     "X-Device-Id": self.device_id},
        )
