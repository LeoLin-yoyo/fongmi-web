"""123 云盘客户端（移植 YunX Pan123Api 协议，Python/httpx 重写）。

链路：/b/api/share/get 匿名列目录 → /b/api/share/download/info 取直链（登录 + CRC32 签名）
→ 解码 DownloadURL（base64 / download-v2 params）→ 跟随 redirect_url。
登录：user.123pan.cn 账号密码换 authorToken（Bearer）；loginuuid 为本地持久化的 32hex 设备标识。
"""
import base64
import json
import os
import random
import re
import time
import zlib
from urllib.parse import quote, unquote

from ..base import PanClient
from ..models import DownloadLink, PanError, ShareFile, ShareSession

API_BASE = "https://yun.123pan.cn"
DOWNLOAD_BASE = "https://www.123865.com"
USER_BASE = "https://user.123pan.cn"
SHARE_GET = f"{API_BASE}/b/api/share/get"
SHARE_DOWNLOAD_INFO = f"{DOWNLOAD_BASE}/b/api/share/download/info"
DOWNLOAD_REFERER = "https://yun.123pan.cn/"
WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36")
DART_UA = "Dart/3.12 (dart:io)"
SIGN_TABLE = "adefghlmyijnopkqrstubcvwsz"
SIGN_OFFSET = 57600
SIGN_OS = "web"
SIGN_VER = "3"


class Pan123Client(PanClient):
    platform = "pan123"
    label = "123云盘"
    REQUIRED_COOKIES = ()
    GUEST_SUPPORTED = False  # 列表匿名，取链需登录

    def __init__(self, cookie="", cookie_sink=None):
        super().__init__(cookie, cookie_sink)
        # cookie 字段存 authorToken（或含 loginuuid 的 JSON）
        self.token = ""
        self.loginuuid = ""
        self._parse_credential(cookie)

    def _parse_credential(self, raw: str):
        if not raw:
            return
        try:
            d = json.loads(raw)
            self.token = d.get("token") or d.get("authorToken") or ""
            self.loginuuid = d.get("loginuuid") or ""
        except (ValueError, TypeError):
            self.token = raw.strip()
        if not self.loginuuid:
            self.loginuuid = self._load_or_make_device_id()

    @staticmethod
    def _load_or_make_device_id() -> str:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "data", ".secret", "pan123_device")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if os.path.isfile(path):
                val = open(path).read().strip()
                if re.fullmatch(r"[0-9a-fA-F]{32}", val):
                    return val
        except OSError:
            pass
        val = "".join(random.choice("0123456789abcdef") for _ in range(32))
        try:
            open(path, "w").write(val)
        except OSError:
            pass
        return val

    @classmethod
    def is_valid_cookie(cls, cookie: str) -> bool:
        if not cookie:
            return False
        try:
            d = json.loads(cookie)
            return bool(d.get("token") or d.get("authorToken"))
        except (ValueError, TypeError):
            return len(cookie.strip()) > 20

    def api_user_agent(self) -> str:
        return WEB_UA

    # ---------- 签名 ----------
    def _make_sign(self, path: str, ts: int = None) -> tuple[str, str]:
        ts = ts or int(time.time())
        t = ts + SIGN_OFFSET
        gm = time.gmtime(t)
        raw = f"{gm.tm_year:04d}{gm.tm_mon:02d}{gm.tm_mday:02d}{gm.tm_hour:02d}{gm.tm_min:02d}"
        mapped = "".join(SIGN_TABLE[int(ch)] for ch in raw)
        auth_key = format(zlib.crc32(mapped.encode()) & 0xffffffff, "x")
        rnd = random.randint(0, 9999999)
        data = f"{ts}|{rnd}|{path}|{SIGN_OS}|{SIGN_VER}|{auth_key}"
        auth_value = f"{ts}-{rnd}-{format(zlib.crc32(data.encode()) & 0xffffffff, 'x')}"
        return auth_key, auth_value

    def _signed_headers(self, path: str, platform: str = "android", app_version: str = "39") -> dict:
        auth_key, auth_value = self._make_sign(path)
        h = {
            "User-Agent": WEB_UA, "platform": platform, "app-version": app_version,
            "authorization": f"Bearer {self.token}", "loginuuid": self.loginuuid,
            "auth-key": auth_key, "auth-value": auth_value,
            "Content-Type": "application/json; charset=utf-8",
        }
        return h

    # ---------- 账号 ----------
    async def fetch_nickname(self) -> str:
        path = "/b/api/user/info"
        auth_key, auth_value = self._make_sign(path)
        self._ensure_proxy()
        resp = await self._client.get(
            f"{API_BASE}{path}",
            headers={"User-Agent": WEB_UA, "platform": "web", "app-version": "3",
                     "authorization": f"Bearer {self.token}", "loginuuid": self.loginuuid,
                     "auth-key": auth_key, "auth-value": auth_value})
        data = resp.json()
        if int(data.get("code") or 0) != 0:
            raise PanError(data.get("message") or "123 账号信息获取失败")
        return str((data.get("data") or {}).get("nickname") or "")

    async def refresh_session(self):
        pass

    # ---------- 分享解析 ----------
    async def create_session(self, share_id: str, passcode: str = "") -> ShareSession:
        return ShareSession(platform=self.platform, share_id=share_id, passcode=passcode or "")

    async def list_share_files(self, session: ShareSession, pdir_fid: str = "0",
                               page: int = 1, size: int = 100) -> list[ShareFile]:
        from urllib.parse import urlencode
        params = {
            "limit": size,
            "next": "0",
            "orderBy": "file_name",
            "orderDirection": "asc",
            "shareKey": session.share_id,
            "ParentFileId": pdir_fid or "0",
            "Page": page,
        }
        if session.raw.get("next"):
            params["next"] = session.raw["next"]
        if session.passcode:
            params["SharePwd"] = session.passcode
        url = f"{SHARE_GET}?{urlencode(params)}"
        self._ensure_proxy()
        resp = await self._client.get(url, headers={"User-Agent": DART_UA})
        data = resp.json()
        if int(data.get("code") or 0) != 0:
            raise PanError(data.get("message") or "123 列目录失败")
        d = data.get("data") or {}
        if d.get("Expired") is True:
            raise PanError("123 分享已失效")
        session.raw["next"] = str(d.get("Next") or "-1")
        files = []
        for item in d.get("InfoList") or []:
            isdir = int(item.get("Type") or 0) == 1
            token = f"{item.get('S3KeyFlag')}|{item.get('Etag')}|{item.get('StorageNode')}"
            files.append(ShareFile(
                fid=str(item.get("FileId") or ""),
                fname=str(item.get("FileName") or ""),
                fsize=int(item.get("Size") or 0),
                isdir=isdir,
                pdir_fid=str(item.get("ParentFileId") or "0"),
                fid_token=token,
                updated_at=str(item.get("UpdateAt") or ""),
            ))
        return files

    # ---------- 取直链 ----------
    async def get_share_download_link(self, session: ShareSession, file: ShareFile) -> DownloadLink:
        if not self.token:
            raise PanError("下载需要先登录123云盘（设置 → 网盘账号）")
        parts = (file.fid_token or "").split("|")
        s3key_flag = parts[0] if len(parts) > 0 else ""
        etag = parts[1] if len(parts) > 1 else ""
        body = {
            "ShareKey": session.share_id, "FileID": file.fid,
            "S3KeyFlag": s3key_flag, "Size": file.fsize, "Etag": etag,
        }
        path = "/b/api/share/download/info"
        self._ensure_proxy()
        resp = await self._client.post(SHARE_DOWNLOAD_INFO, json=body,
                                       headers=self._signed_headers(path, "android", "39"))
        data = resp.json()
        if int(data.get("code") or 0) != 0:
            raise PanError(data.get("message") or "123 获取下载链接失败")
        raw_url = str((data.get("data") or {}).get("DownloadURL") or "")
        direct = self._decode_download_url(raw_url)
        if not direct:
            raise PanError("未返回下载链接")
        return DownloadLink(
            fid=file.fid, filename=file.fname, url=direct, size=file.fsize,
            headers={"User-Agent": DART_UA, "Referer": DOWNLOAD_REFERER},
        )

    def _decode_download_url(self, raw: str) -> str:
        if not raw:
            return ""
        # 形态1：整段 base64
        if "://" not in raw:
            try:
                decoded = base64.b64decode(raw).decode("utf-8", "replace")
                if decoded.startswith("http"):
                    return decoded
            except Exception:
                pass
        # 形态2：...download-v2?params=<base64url>
        if "params=" in raw:
            seg = raw.split("params=", 1)[1].split("&", 1)[0]
            seg = seg.replace("-", "+").replace("_", "/")
            seg += "=" * (-len(seg) % 4)
            try:
                decoded = base64.b64decode(seg).decode("utf-8", "replace")
                if decoded.startswith("http"):
                    return decoded
            except Exception:
                pass
        return raw if raw.startswith("http") else ""
