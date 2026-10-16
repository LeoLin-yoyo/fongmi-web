"""115 网盘客户端（移植 YunX Pan115Api 协议，Python/httpx 重写）。

链路：share/snap（列表匿名可读）→ share/downurl 取直链（需登录 Cookie，且必须客户端 UA）；
大文件走 proapi downurl 加密接口。CDN Cookie 必须回带（缺则 403 no cookie value）。
"""
import re
from urllib.parse import quote

from ..base import PanClient
from ..models import DownloadLink, PanError, ShareFile, ShareSession
from . import pan115_crypto

API_BASE = "https://webapi.115.com"
PROAPI = "https://proapi.115.com/app/chrome/downurl"
SHARE_HOST = "https://115cdn.com"
REFERER = "https://115.com/"
WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36")
CLIENT_UA_DEFAULT = "Mozilla/5.0 115Browser/36.0.1"


class Pan115Client(PanClient):
    platform = "pan115"
    label = "115网盘"
    REQUIRED_COOKIES = ("UID", "SEID")
    GUEST_SUPPORTED = False  # 列表匿名可读，但取 ChainUrl 需登录

    def __init__(self, cookie="", cookie_sink=None):
        super().__init__(cookie, cookie_sink)
        self.client_ua = CLIENT_UA_DEFAULT
        self.user_id = self._extract_user_id()

    def api_user_agent(self) -> str:
        return WEB_UA

    def _extract_user_id(self) -> str:
        m = re.search(r"(?:^|;\s*)UID=([^;]+)", self.cookie or "")
        return m.group(1).split("_")[0] if m else ""

    def _share_referer(self, share_code: str, receive_code: str = "") -> str:
        if receive_code:
            return f"{SHARE_HOST}/s/{share_code}?password={receive_code}&"
        return f"{SHARE_HOST}/s/{share_code}"

    def _base_headers(self, referer: str, cookie: str | None = None) -> dict:
        h = {
            "User-Agent": WEB_UA,
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": referer,
        }
        ck = cookie if cookie is not None else self.cookie
        if ck:
            h["Cookie"] = ck
        return h

    # ---------- 账号 ----------
    async def fetch_nickname(self) -> str:
        self._ensure_proxy()
        resp = await self._client.get(f"{API_BASE}/user/info?ct=json",
                                      headers=self._base_headers(REFERER))
        data = resp.json()
        if int(data.get("errno") or 0) == 990001:
            raise PanError("115 登录已过期，请重新登录", 990001)
        return str(data.get("data") or "")

    async def refresh_session(self):
        pass

    # ---------- 分享解析 ----------
    async def create_session(self, share_id: str, passcode: str = "") -> ShareSession:
        return ShareSession(platform=self.platform, share_id=share_id, passcode=passcode or "")

    async def list_share_files(self, session: ShareSession, pdir_fid: str = "0",
                               page: int = 1, size: int = 100) -> list[ShareFile]:
        offset = (page - 1) * size
        cid = pdir_fid or "0"
        url = (f"{API_BASE}/share/snap?share_code={session.share_id}"
               f"&receive_code={quote(session.passcode or '', safe='')}"
               f"&offset={offset}&limit={size}&asc=0&cid={cid}&format=json")
        referer = self._share_referer(session.share_id, session.passcode)
        self._ensure_proxy()
        resp = await self._client.get(url, headers=self._base_headers(referer))
        data = resp.json()
        self._check(data)
        d = data.get("data") or {}
        share_state = d.get("share_state")
        if share_state in ("1", 1):
            raise PanError("115 分享已失效或被删除")
        if not session.raw.get("user_id"):
            session.raw["user_id"] = str(((d.get("userinfo") or {}).get("user_id")) or "")
            session.title = ((d.get("shareinfo") or {}).get("share_title")) or ""
        files = []
        for item in d.get("list") or []:
            isdir = str(item.get("sha", "")) == "" and "fid" not in item
            files.append(ShareFile(
                fid=str(item.get("fid") or item.get("cid") or ""),
                fname=str(item.get("n") or ""),
                fsize=int(item.get("s") or 0),
                isdir=not item.get("fid"),  # 文件夹无 fid，其 id 在 cid
                pdir_fid=str(item.get("cid") or ""),
                fid_token=str(item.get("pc") or ""),  # pickcode
                updated_at=str(item.get("t") or ""),
            ))
        return files

    def _check(self, data: dict):
        if data.get("state") is True:
            return
        code = int(data.get("errno") or data.get("errNo") or 0)
        msg = {
            990001: "115 登录已过期，请重新登录115网盘",
            4100012: "该分享需要访问码，请填写访问码后重试",
            4100008: "访问码错误，请检查后重试",
            4100026: "分享链接不存在或已被删除",
            50028: "文件大小超出限制，请使用115电脑端下载",
            50029: "当前版本过低，请升级到最新版本下载",
        }.get(code, data.get("error") or data.get("msg") or "115 接口错误")
        raise PanError(f"{msg}（errno={code}）" if code else msg, code)

    # ---------- 取直链 ----------
    def _cdn_cookie(self, resp) -> str:
        """响应头 Set-Cookie 中 path != / 的那条即下载专用 Cookie（约 900s）。

        httpx 的 Headers 用 get_list 取同名多值；缺则退化为单值扫描。
        """
        picked = ""
        headers = resp.headers
        try:
            cookies = headers.get_list("set-cookie")
        except AttributeError:
            v = headers.get("set-cookie")
            cookies = [v] if v else []
        for v in cookies:
            kv = v.split(";", 1)[0].strip()
            m = re.search(r"path=([^;]+)", v, re.I)
            if m and m.group(1).strip() != "/":
                picked = kv
        return picked

    async def get_share_download_link(self, session: ShareSession, file: ShareFile) -> DownloadLink:
        if not self.cookie:
            raise PanError("下载需要先登录115网盘（设置 → 网盘账号）")
        user_id = session.raw.get("user_id") or self.user_id
        referer = self._share_referer(session.share_id, session.passcode)
        url = (f"{API_BASE}/share/downurl?dl=1&user_id={user_id}"
               f"&share_code={session.share_id}&file_id={file.fid}"
               f"&receive_code={quote(session.passcode or '', safe='')}")
        headers = self._base_headers(referer)
        headers["User-Agent"] = self.client_ua
        self._ensure_proxy()
        resp = await self._client.get(url, headers=headers)
        cdn_cookie = self._cdn_cookie(resp)
        data = resp.json()
        if int(data.get("errno") or 0) == 50028:
            # 大文件：走电脑端加密接口
            return await self._proapi_link(file, referer)
        self._check(data)
        d = data.get("data") or {}
        direct = d.get("file_url_302") or (d.get("file_url") if isinstance(d.get("file_url"), str) else "") or ""
        if not direct and isinstance(d.get("url"), dict):
            direct = d["url"].get("url") or ""
        if not direct:
            raise PanError("未返回下载链接")
        cookie_header = self.cookie
        if cdn_cookie:
            cookie_header = f"{self.cookie}; {cdn_cookie}"
        return DownloadLink(
            fid=file.fid, filename=str(d.get("fn") or file.fname),
            url=direct, size=int(d.get("fs") or file.fsize),
            headers={"User-Agent": self.client_ua, "Referer": REFERER,
                     "Cookie": cookie_header, "X-Requested-With": "XMLHttpRequest"},
        )

    async def _proapi_link(self, file: ShareFile, referer: str) -> DownloadLink:
        """电脑端加密接口（大文件）：POST proapi downurl，data=加密(pickcode)。"""
        pickcode = file.fid_token
        import time
        payload = pan115_crypto.encode(f'{{"pickcode":"{pickcode}"}}')
        body = f"data={quote(payload, safe='')}"
        headers = {
            "User-Agent": self.client_ua,
            "Referer": referer,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        self._ensure_proxy()
        resp = await self._client.post(f"{PROAPI}?t={int(time.time())}",
                                       content=body, headers=headers)
        cdn_cookie = self._cdn_cookie(resp)
        data = resp.json()
        self._check(data)
        decrypted = pan115_crypto.decode(str(data.get("data") or ""))
        import json
        obj = json.loads(decrypted)
        entry = next(iter(obj.values()), {})
        direct = ((entry.get("url") or {}).get("url")) or ""
        if not direct:
            raise PanError("未返回下载链接")
        cookie_header = f"{self.cookie}; {cdn_cookie}" if cdn_cookie else self.cookie
        return DownloadLink(
            fid=file.fid, filename=str(entry.get("file_name") or file.fname),
            url=direct, size=int(entry.get("file_size") or file.fsize),
            headers={"User-Agent": self.client_ua, "Referer": REFERER,
                     "Cookie": cookie_header},
        )
