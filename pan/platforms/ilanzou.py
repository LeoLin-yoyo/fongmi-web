"""蓝奏云优享版客户端（移植 YunX ILanzouApi 协议，Python/httpx 重写）。

链路：/unproved/share/list 匿名列目录 → /unproved/file/redirect 取直链。
参数走 URL query（uuid/devType/devCode/devModel/devVersion/timestamp），
timestamp/downloadId/auth 用 AES-ECB(lanZouY-disk-app) → 小写 hex。
"""
import base64
import json
import random
import time
from urllib.parse import quote

from Crypto.Cipher import AES

from ..base import PanClient
from ..models import DownloadLink, PanError, ShareFile, ShareSession

API_BASE = "https://apis.ilanzou.com"
SHARE_API_BASE = "https://apix.ilanzou.com"
WEB_SITE = "https://www.ilanzou.com"
WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
AES_KEY = b"lanZouY-disk-app"  # 16B
DEV_TYPE = "6"
DEV_VERSION = "125"
PAGE_SIZE = 60


def _aes_hex(text: str) -> str:
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    data = text.encode("utf-8")
    padlen = 16 - len(data) % 16
    data += bytes([padlen]) * padlen
    return cipher.encrypt(data).hex()


def _enc_token(text: str) -> str:
    # 标准 URL 编码后把 %3A 还原为冒号
    return quote(text, safe="").replace("%3A", ":")


class ILanzouClient(PanClient):
    platform = "ilanzou"
    label = "蓝奏云优享版"
    REQUIRED_COOKIES = ()
    GUEST_SUPPORTED = True
    GUEST_MAX_BYTES = 0

    def __init__(self, cookie="", cookie_sink=None):
        super().__init__(cookie, cookie_sink)
        self.uuid = ""
        self.app_token = ""
        self._parse(cookie)

    def _parse(self, raw: str):
        if not raw:
            return
        try:
            d = json.loads(raw)
            self.uuid = d.get("uuid") or ""
            self.app_token = d.get("appToken") or d.get("app_token") or ""
        except (ValueError, TypeError):
            self.app_token = raw.strip()
        if not self.uuid:
            self.uuid = "".join(random.choice("0123456789abcdef") for _ in range(32))

    @classmethod
    def is_valid_cookie(cls, cookie: str) -> bool:
        if not cookie:
            return False
        try:
            d = json.loads(cookie)
            return bool(d.get("appToken") or d.get("app_token"))
        except (ValueError, TypeError):
            return len(cookie.strip()) > 16

    def api_user_agent(self) -> str:
        return WEB_UA

    def _browser_headers(self, post: bool = False) -> dict:
        h = {
            "User-Agent": WEB_UA,
            "Origin": WEB_SITE,
            "Referer": f"{WEB_SITE}/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
        }
        if post:
            h["Content-Type"] = "application/json; charset=utf-8"
        return h

    def _common_query(self, extra: dict, token: str = "", dev_model: str = "chrome") -> str:
        parts = {
            "uuid": self.uuid, "devType": DEV_TYPE, "devCode": self.uuid,
            "devModel": dev_model, "devVersion": DEV_VERSION, "appVersion": "",
            "timestamp": _aes_hex(str(int(time.time() * 1000))),
        }
        if token:
            parts["appToken"] = token
        parts.update(extra)
        return "&".join(f"{k}={_enc_token(str(v))}" for k, v in parts.items())

    async def fetch_nickname(self) -> str:
        url = f"{API_BASE}/proved/user/account/map?{self._common_query({}, self.app_token)}"
        self._ensure_proxy()
        resp = await self._client.get(url, headers=self._browser_headers())
        d = resp.json()
        self._check(d)
        return str((d.get("data") or {}).get("nickName") or "")

    async def refresh_session(self):
        pass

    def _check(self, data: dict):
        code = data.get("code")
        if code == 200:
            return
        if code in (-1, -2):
            raise PanError("蓝奏优享登录已过期，请重新登录", int(code))
        raise PanError(data.get("msg") or f"蓝奏优享请求失败（code={code}）",
                       int(code) if isinstance(code, int) else 0)

    # ---------- 分享解析 ----------
    async def create_session(self, share_id: str, passcode: str = "") -> ShareSession:
        return ShareSession(platform=self.platform, share_id=share_id, passcode=passcode or "")

    async def list_share_files(self, session: ShareSession, pdir_fid: str = "",
                               page: int = 1, size: int = PAGE_SIZE) -> list[ShareFile]:
        extra = {"extra": "2", "shareId": session.share_id, "offset": page, "limit": size}
        if pdir_fid:
            extra["folderId"] = pdir_fid
        query = self._common_query(extra, dev_model="Chrome")
        url = f"{SHARE_API_BASE}/unproved/share/list?{query}"
        self._ensure_proxy()
        resp = await self._client.get(url, headers=self._browser_headers())
        data = resp.json()
        if data.get("code") != 200:
            raise PanError(data.get("msg") or f"蓝奏优享分享请求失败（code={data.get('code')}）")
        d = data.get("data") or data
        lst = d.get("list") or d.get("records") or []
        return [self._parse_file(i) for i in lst]

    @staticmethod
    def _parse_file(item: dict) -> ShareFile:
        isdir = int(item.get("fileType") or 0) == 2
        return ShareFile(
            fid=str(item.get("fileId") or item.get("folderId") or ""),
            fname=str(item.get("fileName") or item.get("folderName") or ""),
            fsize=int(item.get("fileSize") or 0) * 1024 if item.get("fileSize") else 0,  # KiB→B
            isdir=isdir,
            pdir_fid=str(item.get("folderId") or ""),
            updated_at=str(item.get("updTime") or item.get("addTime") or ""),
        )

    async def get_share_download_link(self, session: ShareSession, file: ShareFile) -> DownloadLink:
        ts = int(time.time() * 1000)
        extra = {
            "downloadId": _aes_hex(f"{file.fid}|"),
            "enable": "1",
            "devType": DEV_TYPE,
            "uuid": self.uuid,
            "timestamp": _aes_hex(str(ts)),
            "auth": _aes_hex(f"{file.fid}|{ts}"),
            "shareId": session.share_id,
        }
        query = "&".join(f"{k}={_enc_token(str(v))}" for k, v in extra.items())
        url = f"{SHARE_API_BASE}/unproved/file/redirect?{query}"
        self._ensure_proxy()
        resp = await self._client.get(url, headers=self._browser_headers())
        if resp.status_code in (300, 301, 302, 303, 307, 308):
            loc = resp.headers.get("location") or ""
            if loc:
                direct = loc if loc.startswith("http") else f"{SHARE_API_BASE}{loc}"
                return DownloadLink(fid=file.fid, filename=file.fname, url=direct,
                                    size=file.fsize,
                                    headers={"User-Agent": WEB_UA, "Referer": f"{WEB_SITE}/",
                                             "Origin": WEB_SITE})
        data = resp.json()
        if data.get("code") != 200:
            raise PanError(data.get("msg") or "蓝奏优享未返回下载地址")
        d = data.get("data") or data
        direct = d.get("url") or (d.get("data") or {}).get("url") or ""
        if not direct:
            raise PanError("蓝奏优享未返回下载地址，请检查文件权限")
        return DownloadLink(fid=file.fid, filename=file.fname, url=direct, size=file.fsize,
                            headers={"User-Agent": WEB_UA, "Referer": f"{WEB_SITE}/",
                                     "Origin": WEB_SITE})
