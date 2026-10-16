"""UC 网盘客户端（移植 YunX UCApi 协议，Python/httpx 重写）。

与夸克同 quark 系代码：差异在列表用 transfer_share/detail（GET，stoken 绑定 fid_token）、
取链同端点、游客风控更严（专用 GUEST_UA + Sec-Ch-Ua）、
视频优先 video_preview 原画直链（绕过非会员宣传片替换）。
"""
from urllib.parse import quote

from ..base import PanClient
from ..cookies import pugs_from_set_cookies, without_puus
from ..models import DownloadLink, PanError, ShareFile, ShareSession

API_BASE = "https://pc-api.uc.cn"
WEB = "https://drive.uc.cn"
FAST = "https://fast.uc.cn"
WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/120.0.0.0 Safari/537.36")
GUEST_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "uc-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 "
            "Safari/537.36 Channel/pckk_other_ch")
GUEST_SEC_CH_UA = '"Not=A?Brand";v="99", "Chromium";v="100", "Google Chrome";v="100"'

SHARE_TOKEN_URL = f"{API_BASE}/1/clouddrive/share/sharepage/token?pr=UCBrowser&fr=pc"
TRANSFER_SHARE_DETAIL_URL = f"{API_BASE}/1/clouddrive/transfer_share/detail?entry=ft&fr=pc&pr=UCBrowser"
DOWNLOAD_URL = f"{API_BASE}/1/clouddrive/file/download?entry=ft&fr=pc&pr=UCBrowser"
VIDEO_PREVIEW_URL = f"{API_BASE}/1/clouddrive/share/sharepage/video_preview"
ACCOUNT_INFO_URL = f"{WEB}/account/info"
CONFIG_URL = f"{API_BASE}/1/clouddrive/config?pr=UCBrowser&fr=pc"
DOWNLOAD_REFERER = f"{WEB}/"

VIDEO_EXT = {"mp4", "mkv", "avi", "mov", "wmv", "flv", "ts", "rmvb", "webm", "m4v"}


class UCClient(PanClient):
    platform = "uc"
    label = "UC网盘"
    REQUIRED_COOKIES = ("__pus", "__puus")
    GUEST_SUPPORTED = True
    GUEST_MAX_BYTES = 0  # UC 游客实测不限大小

    def __init__(self, cookie: str = "", cookie_sink=None):
        super().__init__(cookie, cookie_sink)
        self.guest_pugs = ""

    def api_user_agent(self) -> str:
        return WEB_UA

    # ---------- 账号 ----------
    async def fetch_nickname(self) -> str:
        data = await self.get_json(ACCOUNT_INFO_URL)
        if data.get("success") is True:
            return (data.get("data") or {}).get("nickname") or ""
        return ""

    async def refresh_session(self):
        try:
            await self.get_json(CONFIG_URL, cookie=without_puus(self.cookie))
        except PanError:
            pass

    # ---------- 分享解析 ----------
    async def create_session(self, share_id: str, passcode: str = "") -> ShareSession:
        body = {"pwd_id": share_id, "passcode": passcode or "", "share_for_transfer": True}
        data = await self.post_json(SHARE_TOKEN_URL, body)
        stoken = data.get("stoken") or ""
        if not stoken:
            raise PanError("获取分享 token 失败：stoken 为空")
        return ShareSession(platform=self.platform, share_id=share_id,
                            passcode=passcode or "", stoken=stoken,
                            title=data.get("title") or "",
                            first_fid=data.get("first_fid") or "0")

    async def list_share_files(self, session: ShareSession, pdir_fid: str = "0",
                               page: int = 1, size: int = 50) -> list[ShareFile]:
        """transfer_share/detail：GET + stoken → share_fid_token 与 stoken 绑定，download 才能过校验。"""
        url = (f"{TRANSFER_SHARE_DETAIL_URL}&pwd_id={session.share_id}"
               f"&pdir_fid={pdir_fid}&fetch_file_list=1&passcode="
               f"&_page={page}&_size={size}&_fetch_total=1&_fetch_task=1&_fetch_share=1&_sort="
               f"&stoken={quote(session.stoken, safe='')}")
        data = await self.get_json(url, headers={
            "Origin": FAST, "Referer": f"{FAST}/",
        })
        items = data.get("list")
        if items is None:
            items = (data.get("detail_info") or {}).get("list") or []
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
        if guest_cookie:
            ck = f"{self.cookie}; {guest_cookie}" if self.cookie else guest_cookie
        else:
            ck = self.cookie
        return {"Referer": DOWNLOAD_REFERER, "Cookie": ck, "User-Agent": WEB_UA}

    async def get_share_download_link(self, session: ShareSession,
                                      file: ShareFile) -> DownloadLink:
        """官方流程：无需转存，分享 fid + fid_token + stoken + pwd_id 直接换直链。

        视频先走 video_preview 取原画直链（登录态），失败回落普通 download。
        """
        ext = file.fname.rsplit(".", 1)[-1].lower() if "." in file.fname else ""
        if ext in VIDEO_EXT and self.cookie:
            preview = await self._video_preview(session, file)
            if preview:
                return preview
        body = {
            "fids": [file.fid],
            "pwd_id": session.share_id,
            "stoken": session.stoken,
            "fids_token": [file.fid_token],
        }
        data = await self.post_json(DOWNLOAD_URL, body)
        status = int(data.get("status") or 0)
        code = int(data.get("code") or 0)
        if status != 200 and code != 0:
            if code == 31001:
                raise PanError("UC登录态已失效，请重新粘贴 Cookie", code)
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

    async def _video_preview(self, session: ShareSession, file: ShareFile) -> DownloadLink | None:
        """分享视频预览原画直链（约 3 小时有效）；失败返回 None 由调用方回落。"""
        url = (f"{VIDEO_PREVIEW_URL}?pr=UCBrowser&fr=h5"
               f"&pwd_id={quote(session.share_id, safe='')}"
               f"&stoken={quote(session.stoken, safe='')}"
               f"&fid={quote(file.fid, safe='')}"
               f"&fid_token={quote(file.fid_token, safe='')}")
        try:
            data = await self.get_json(url, headers={
                "Origin": WEB, "Referer": DOWNLOAD_REFERER,
            })
            if int(data.get("status") or 0) != 200 and int(data.get("code") or 0) != 0:
                return None
            play = (data.get("data") or {}).get("play_info") or {}
            u = play.get("url") or ""
            if not u:
                return None
            return DownloadLink(
                fid=file.fid, filename=file.fname, url=u,
                size=int(play.get("size") or file.fsize),
                headers=self._download_headers(),
            )
        except PanError:
            return None

    async def get_guest_download_link(self, session: ShareSession,
                                      file: ShareFile) -> DownloadLink:
        """游客取链：同端点不带账号 Cookie，用 GUEST_UA + Sec-Ch-Ua；响应 __pugs 必须回带。"""
        body = {
            "fids": [file.fid],
            "pwd_id": session.share_id,
            "stoken": session.stoken,
            "fids_token": [file.fid_token],
        }
        h = {"Content-Type": "application/json", "User-Agent": GUEST_UA,
             "Sec-Ch-Ua": GUEST_SEC_CH_UA}
        if self.guest_pugs:
            h["Cookie"] = self.guest_pugs
        self._ensure_proxy()
        resp = await self._client.post(DOWNLOAD_URL, json=body, headers=h)
        response_pugs = pugs_from_set_cookies(
            [v for k, v in resp.headers.items() if k.lower() == "set-cookie"])
        text = resp.text
        if response_pugs:
            self.guest_pugs = response_pugs
        try:
            data = __import__("json").loads(text)
        except Exception:
            raise PanError(f"响应解析失败（HTTP {resp.status_code}）")
        code = int(data.get("code") or 0)
        if int(data.get("status") or 0) != 200 and code != 0:
            msg = {
                31001: "该分享需要登录 UC 网盘后才能下载",
                23018: "该文件超出游客可获取的大小上限，请先登录 UC 网盘",
                14001: "分享已失效或提取码有误，请重新解析",
                41020: "文件令牌已过期，请重新解析分享",
            }.get(code, data.get("message") or "获取下载链接失败")
            raise PanError(msg, code)
        items = data.get("data") or []
        if not items:
            raise PanError("未返回下载链接")
        item = items[0]
        link = DownloadLink(
            fid=str(item.get("fid", "")),
            filename=str(item.get("file_name") or item.get("filename") or file.fname),
            url=str(item.get("download_url", "")),
            size=int(item.get("size") or file.fsize),
        )
        link.guest_cookie = response_pugs or self.guest_pugs
        link.headers = self._download_headers(guest_cookie=link.guest_cookie)
        return link
