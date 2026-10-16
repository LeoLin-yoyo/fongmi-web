"""夸克网盘客户端（移植 YunX QuarkApi 协议，Python/httpx 重写）。

链路：token(stoken) → sharepage/detail 列目录 → file/download 免转存取分享直链。
会话保鲜：所有响应 Set-Cookie 的 __puus/__pus 合并回账号 Cookie 并回写 sink。
直链铁律：download_url 签名绑定取链时刻 Cookie → 请求必带 headers，302=失效。
"""
from urllib.parse import quote

from ..base import PanClient
from ..cookies import pugs_from_set_cookies, without_puus
from ..models import DownloadLink, PanError, ShareFile, ShareSession

API_BASE = "https://drive-pc.quark.cn"
WEB = "https://pan.quark.cn"
API_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.12-a038f7b798 "
          "Safari/537.36 Channel/pckk_other_ch")

SHARE_TOKEN_URL = f"{API_BASE}/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc"
SHARE_DETAIL_URL = f"{API_BASE}/1/clouddrive/share/sharepage/detail?pr=ucpro&fr=pc"
DOWNLOAD_URL = f"{API_BASE}/1/clouddrive/file/download?pr=ucpro&fr=pc&sys=win32&ve=3.23.2"
ACCOUNT_INFO_URL = f"{WEB}/account/info"
CONFIG_URL = f"{API_BASE}/1/clouddrive/config?pr=ucpro&fr=pc"
DOWNLOAD_REFERER = f"{WEB}/"

QUARK_VIDEO_EXT = {"mp4", "mkv", "avi", "mov", "wmv", "flv", "ts", "rmvb", "webm", "m4v"}


class QuarkClient(PanClient):
    platform = "quark"
    label = "夸克网盘"
    REQUIRED_COOKIES = ("__pus", "__puus")
    GUEST_SUPPORTED = True
    GUEST_MAX_BYTES = 50 * 1024 * 1024  # 游客取链实测上限约 50MB（23018）

    def __init__(self, cookie: str = "", cookie_sink=None):
        super().__init__(cookie, cookie_sink)
        self.guest_pugs = ""

    def api_user_agent(self) -> str:
        return API_UA

    def _web_headers(self) -> dict:
        return {"Origin": WEB, "Referer": DOWNLOAD_REFERER}

    # ---------- 账号 ----------
    async def fetch_nickname(self) -> str:
        data = await self.get_json(ACCOUNT_INFO_URL)
        if data.get("success") is True:
            return (data.get("data") or {}).get("nickname") or ""
        return ""

    async def refresh_session(self):
        """剥离 __puus 请求 /config 触发服务端重新下发（AList refreshPuus 口径）。"""
        try:
            await self.get_json(CONFIG_URL, headers=self._web_headers(),
                                cookie=without_puus(self.cookie))
        except PanError:
            pass

    # ---------- 分享解析 ----------
    async def create_session(self, share_id: str, passcode: str = "") -> ShareSession:
        body = {"pwd_id": share_id, "passcode": passcode or "",
                "support_visit_limit_private_share": True}
        data = await self.post_json(SHARE_TOKEN_URL, body)
        stoken = data.get("stoken") or ""
        if not stoken:
            raise PanError("获取分享 token 失败：stoken 为空")
        return ShareSession(platform=self.platform, share_id=share_id,
                            passcode=passcode or "", stoken=stoken,
                            title=data.get("title") or "",
                            first_fid=data.get("first_fid") or "0")

    async def list_share_files(self, session: ShareSession, pdir_fid: str = "0",
                               page: int = 1, size: int = 100) -> list[ShareFile]:
        url = (f"{SHARE_DETAIL_URL}&pwd_id={session.share_id}"
               f"&stoken={quote(session.stoken, safe='')}"
               f"&pdir_fid={pdir_fid}&ver=2&force=0&_page={page}&_size={size}"
               f"&_fetch_banner=0&_fetch_share=0&fetch_relate_conversation=0&_fetch_total=1"
               f"&_sort=file_type:asc,file_name:asc")
        data = await self.get_json(url, headers=self._web_headers())
        items = data.get("list") or []
        return [
            ShareFile(
                fid=str(i.get("fid", "")),
                fname=str(i.get("file_name", "")),
                fsize=int(i.get("size") or 0),
                isdir=bool(i.get("dir", False)),
                pdir_fid=str(i.get("pdir_fid", "")),
                fid_token=str(i.get("share_fid_token", "")),
                updated_at=str(i.get("updated_at", "")),
            )
            for i in items
        ]

    # ---------- 取直链 ----------
    def _download_headers(self, guest_cookie: str = "") -> dict:
        """直链请求头：Referer + 当前 Cookie（或游客态 __pugs）。"""
        if guest_cookie:
            ck = guest_cookie
            if self.cookie:
                ck = f"{self.cookie}; {guest_cookie}"
        else:
            ck = self.cookie
        return {"Referer": DOWNLOAD_REFERER, "Cookie": ck, "User-Agent": API_UA}

    async def get_share_download_link(self, session: ShareSession,
                                      file: ShareFile) -> DownloadLink:
        """免转存分享取链（登录态）：download 端点带分享四件套。"""
        body = {
            "fids": [file.fid],
            "fids_token": [file.fid_token],
            "pwd_id": session.share_id,
            "stoken": session.stoken,
            "speedup_session": "",
            "token": "",
        }
        data = await self.post_json(DOWNLOAD_URL, body)
        return self._parse_link(data, file)

    async def get_guest_download_link(self, session: ShareSession,
                                      file: ShareFile) -> DownloadLink:
        """游客取链：同端点不带账号 Cookie，响应下发 __pugs 必须回带。"""
        body = {
            "fids": [file.fid],
            "fids_token": [file.fid_token],
            "pwd_id": session.share_id,
            "stoken": session.stoken,
            "speedup_session": "",
            "token": "",
        }
        h = {"Content-Type": "application/json", "User-Agent": API_UA}
        if self.guest_pugs:
            h["Cookie"] = self.guest_pugs
        self._ensure_proxy()
        resp = await self._client.post(DOWNLOAD_URL, json=body, headers=h)
        pugs = pugs_from_set_cookies(
            [v for k, v in resp.headers.items() if k.lower() == "set-cookie"])
        if pugs:
            self.guest_pugs = pugs
        try:
            data = resp.json()
        except Exception:
            raise PanError(f"响应解析失败（HTTP {resp.status_code}）")
        code = int(data.get("code") or 0)
        if int(data.get("status") or 0) != 200 and code != 0:
            if code == 23018:
                raise PanError("该文件超出游客上限（夸克约 50MB），请先登录夸克网盘")
            if code == 31001:
                raise PanError("该分享需要登录夸克网盘后才能下载")
            raise PanError(data.get("message") or "获取下载链接失败", code)
        link = self._parse_link(data, file)
        link.guest_cookie = pugs or self.guest_pugs
        link.headers = self._download_headers(guest_cookie=link.guest_cookie)
        return link

    def _parse_link(self, data: dict, file: ShareFile) -> DownloadLink:
        """quark/uc 系公共响应校验：status!=200 时按 code 识别（21001=文件不存在，31001=登录态失效）。"""
        status = int(data.get("status") or 0)
        code = int(data.get("code") or 0)
        if status != 200 and code != 0:
            if code == 31001:
                raise PanError(f"{self.label}登录态已失效，请重新粘贴 Cookie", code)
            if code == 21001:
                raise PanError("文件不存在（分享可能已失效）", code)
            raise PanError(data.get("message") or "获取下载链接失败", code)
        items = data.get("data") or []
        if not items:
            raise PanError("未返回下载链接")
        item = items[0]
        return DownloadLink(
            fid=str(item.get("fid", "")),
            filename=str(item.get("file_name") or item.get("filename") or file.fname),
            url=str(item.get("download_url", "")),
            size=int(item.get("size") or file.fsize),
            headers=self._download_headers(),
        )
