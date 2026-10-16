"""光鸭云盘客户端（移植 YunX GuangYaApi 协议，Python/httpx 重写）。

分享链路（匿名）：get_share_summary → get_share_access_token(提取码) → get_share_page_files_list
→ get_share_download_url（signedURL，OBS/OSS 预签名）。
设备头 did/dt/traceparent 必须带；业务码 207=需登录转存。
"""
import os
import random
import secrets

from ..base import PanClient
from ..models import DownloadLink, PanError, ShareFile, ShareSession

API_BASE = "https://api.guangyapan.com"
ACCOUNT_BASE = "https://account.guangyapan.com"
WEB_SITE = "https://www.guangyapan.com"
DOWNLOAD_REFERER = f"{WEB_SITE}/"
WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
CLIENT_ID = "aMe-8VSlkrbQXpUR"
PAGE_SIZE = 100

SHARE_SUMMARY = f"{API_BASE}/userres/v1/get_share_summary"
SHARE_ACCESS_TOKEN = f"{API_BASE}/userres/v1/get_share_access_token"
SHARE_FILES = f"{API_BASE}/userres/v1/get_share_page_files_list"
SHARE_DOWNLOAD = f"{API_BASE}/userres/v1/get_share_download_url"


def _public_device_id() -> str:
    return "".join(random.choice("0123456789abcdef") for _ in range(32))


class GuangYaClient(PanClient):
    platform = "guangya"
    label = "光鸭云盘"
    REQUIRED_COOKIES = ()
    GUEST_SUPPORTED = True
    GUEST_MAX_BYTES = 0

    def __init__(self, cookie="", cookie_sink=None):
        super().__init__(cookie, cookie_sink)
        self.access_token = ""
        self.device_id = _public_device_id()
        self._parse(cookie)

    def _parse(self, raw: str):
        if not raw:
            return
        import json
        try:
            d = json.loads(raw)
            self.access_token = d.get("access_token") or d.get("accessToken") or ""
            self.device_id = d.get("device_id") or self.device_id
        except (ValueError, TypeError):
            self.access_token = raw.strip()

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

    def _business_headers(self, token: str = "") -> dict:
        trace = f"00-{secrets.token_hex(16)}-{secrets.token_hex(8)}-01"
        h = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "User-Agent": WEB_UA,
            "Origin": WEB_SITE,
            "Referer": DOWNLOAD_REFERER,
            "dt": "4",
            "traceparent": trace,
            "did": self.device_id,
        }
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    async def _business_post(self, url: str, body: dict, token: str = "") -> dict:
        self._ensure_proxy()
        resp = await self._client.post(url, json=body, headers=self._business_headers(token))
        try:
            data = resp.json()
        except Exception:
            raise PanError(f"光鸭响应解析失败（HTTP {resp.status_code}）")
        self._check(data, "光鸭请求失败")
        return data

    def _check(self, data: dict, fallback: str):
        if data.get("success") is False:
            raise PanError(data.get("msg") or data.get("message") or fallback)
        code = str(data.get("code") or "")
        if code and code not in ("0",):
            msg = {
                "209": "光鸭分享提取码错误或缺失",
                "200": "光鸭分享已取消、过期或不可访问",
                "201": "光鸭分享已取消、过期或不可访问",
                "202": "光鸭分享已取消、过期或不可访问",
                "205": "光鸭分享下载受限，请在官网确认该分享的下载权限",
                "206": "光鸭分享下载受限，请在官网确认该分享的下载权限",
                "207": "光鸭分享下载受限，请在官网确认该分享的下载权限",
                "504": "光鸭分享下载受限，请在官网确认该分享的下载权限",
                "157": "光鸭网盘空间不足",
            }.get(code, data.get("msg") or data.get("message") or f"{fallback}（code={code}）")
            raise PanError(msg, int(code) if code.isdigit() else 0)
        if data.get("error"):
            raise PanError(str(data.get("error")))

    @staticmethod
    def _data_of(data: dict) -> dict:
        return data.get("data") or data

    # ---------- 账号 ----------
    async def fetch_nickname(self) -> str:
        h = self._business_headers(self.access_token)
        self._ensure_proxy()
        resp = await self._client.get(f"{ACCOUNT_BASE}/v1/user/me", headers=h)
        try:
            d = resp.json()
        except Exception:
            return ""
        return str((d.get("data") or d).get("nickname") or "")

    async def refresh_session(self):
        pass

    # ---------- 分享解析 ----------
    async def create_session(self, share_id: str, passcode: str = "") -> ShareSession:
        title = ""
        try:
            data = await self._business_post(SHARE_SUMMARY, {"shareId": share_id})
            d = self._data_of(data)
            title = str(d.get("title") or d.get("shareName") or "")
        except PanError:
            pass
        access_token = ""
        if passcode:
            data = await self._business_post(SHARE_ACCESS_TOKEN,
                                             {"shareId": share_id, "code": passcode})
            d = self._data_of(data)
            access_token = str(d.get("accessToken") or d.get("access_token") or "")
            if not access_token:
                raise PanError("光鸭分享链接无效或提取码错误")
        return ShareSession(platform=self.platform, share_id=share_id,
                            passcode=passcode or "", stoken=access_token, title=title)

    async def list_share_files(self, session: ShareSession, pdir_fid: str = "",
                               page: int = 1, size: int = PAGE_SIZE) -> list[ShareFile]:
        body = {"parentId": pdir_fid, "pageSize": size, "orderBy": 0, "sortType": 0,
                "accessToken": session.stoken}
        data = await self._business_post(SHARE_FILES, body)
        d = self._data_of(data)
        arr = d.get("list") or d.get("items") or d.get("files") or d.get("records") or d.get("content") or []
        return [self._parse_file(i) for i in arr]

    @staticmethod
    def _parse_file(item: dict) -> ShareFile:
        return ShareFile(
            fid=str(item.get("fileId") or item.get("id") or ""),
            fname=str(item.get("fileName") or item.get("name") or ""),
            fsize=int(item.get("fileSize") or item.get("size") or 0),
            isdir=bool(item.get("isDir")) or int(item.get("fileType") or 0) == 2
                  or str(item.get("resType")) == "folder",
            pdir_fid=str(item.get("parentId") or ""),
            updated_at=str(item.get("updateTime") or item.get("updTime") or ""),
        )

    # ---------- 取直链 ----------
    async def get_share_download_link(self, session: ShareSession, file: ShareFile) -> DownloadLink:
        data = await self._business_post(SHARE_DOWNLOAD,
                                         {"fileId": file.fid, "accessToken": session.stoken})
        d = self._data_of(data)
        url = (d.get("signedURL") or d.get("signedUrl") or d.get("downloadUrl")
               or d.get("download_url") or d.get("url") or d.get("cdnUrl") or "")
        if not url:
            raise PanError("光鸭未返回有效下载地址，请确认下载权限")
        return DownloadLink(
            fid=file.fid, filename=file.fname, url=url,
            size=int(d.get("size") or file.fsize),
            headers={"User-Agent": WEB_UA, "Referer": DOWNLOAD_REFERER},
        )
