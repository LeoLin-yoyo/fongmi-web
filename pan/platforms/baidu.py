"""百度网盘客户端（移植 YunX BaiduApi 协议，Python/httpx 重写）。

链路：share/verify(提取码)→sekey → xpan/share?method=list 列目录 → share/transfer 转存
→ locatedownload 取高速直链（优先 encrypt=0 的明文 appall* 通道）。
登录必需（BDUSS Cookie），不支持游客下载。
"""
from urllib.parse import quote

from ..base import PanClient
from ..models import DownloadLink, PanError, ShareFile, ShareSession

WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/120.0.0.0 Safari/537.36")
UA_NETDISK = "netdisk;P2SP;3.0.20.136;android-android"
APP_ID = "250528"
TEMP_DIR = "/apps/fongmi-web/temp"


class BaiduClient(PanClient):
    platform = "baidu"
    label = "百度网盘"
    REQUIRED_COOKIES = ("BDUSS",)
    GUEST_SUPPORTED = False

    def __init__(self, cookie="", cookie_sink=None):
        super().__init__(cookie, cookie_sink)
        self._bdstoken = ""

    def api_user_agent(self) -> str:
        return WEB_UA

    # ---------- 账号 ----------
    async def _template_variable(self, fields: str) -> dict:
        url = (f"https://pan.baidu.com/api/gettemplatevariable"
               f"?clienttype=0&app_id={APP_ID}&web=1&fields={quote(fields, safe='')}")
        data = await self.get_json(url)
        if int(data.get("errno", 0)) != 0:
            raise PanError(data.get("errmsg") or "百度接口错误")
        return data.get("result") or {}

    async def fetch_nickname(self) -> str:
        r = await self._template_variable('["username"]')
        return (r.get("username") or "").strip()

    async def _get_bdstoken(self) -> str:
        if self._bdstoken:
            return self._bdstoken
        r = await self._template_variable('["bdstoken"]')
        tok = (r.get("bdstoken") or "").strip()
        if not tok:
            raise PanError("获取 bdstoken 失败，请重新登录")
        self._bdstoken = tok
        return tok

    # ---------- 分享解析 ----------
    async def create_session(self, share_id: str, passcode: str = "") -> ShareSession:
        sekey = ""
        if passcode:
            url = f"https://pan.baidu.com/share/verify?surl={share_id}"
            data = await self.post_json(
                url, {}, headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": f"https://pan.baidu.com/s/{share_id}",
                })
            if int(data.get("errno", 0)) != 0:
                raise PanError(data.get("errmsg") or "验证提取码失败")
            sekey = data.get("randsk") or ""
            if not sekey:
                raise PanError("未返回分享密钥（提取码可能错误）")
        return ShareSession(platform=self.platform, share_id=share_id,
                            passcode=passcode or "", stoken=sekey,  # stoken 复用为 sekey
                            raw={"sekey": sekey})

    def _auth_cookie(self, sekey: str) -> str:
        if sekey and "BDCLND=" not in self.cookie:
            return f"{self.cookie}; BDCLND={sekey}"
        return self.cookie

    async def list_share_files(self, session: ShareSession, pdir_fid: str = "/",
                               page: int = 1, size: int = 100) -> list[ShareFile]:
        sekey = session.raw.get("sekey") or ""
        is_root = pdir_fid in ("", "/")
        root = "1" if is_root else "0"
        sekey_part = f"&sekey={sekey}" if sekey else ""
        dirpath = "/" if is_root else pdir_fid
        url = (f"https://pan.baidu.com/rest/2.0/xpan/share?method=list"
               f"&shorturl={session.share_id}&page={page}&num=100&root={root}"
               f"&dir={quote(dirpath, safe='')}{sekey_part}")
        headers = {"Referer": f"https://pan.baidu.com/s/{session.share_id}"}
        resp = await self._client.get(url, headers=self._headers(headers, self._auth_cookie(sekey)))
        try:
            data = resp.json()
        except Exception:
            raise PanError(f"响应解析失败（HTTP {resp.status_code}）")
        errno = int(data.get("errno", 0))
        if errno != 0:
            if not sekey:
                if errno == -6:
                    raise PanError(f"该分享需要提取码，或需要登录百度网盘（errno={errno}）")
                raise PanError(f"该分享需要提取码（errno={errno}）")
            raise PanError(data.get("errmsg") or f"获取分享文件列表失败（errno={errno}）")
        if not session.raw.get("uk"):
            session.raw["uk"] = str(data.get("uk") or "")
            session.raw["share_id"] = str(data.get("share_id") or "")
            session.title = data.get("title") or session.title
        files = []
        for item in data.get("list") or []:
            isdir = str(item.get("isdir")) == "1"
            path = str(item.get("path") or "")
            files.append(ShareFile(
                fid=path if isdir else str(item.get("fs_id") or ""),
                fname=str(item.get("server_filename") or ""),
                fsize=int(item.get("size") or 0),
                isdir=isdir,
                pdir_fid=path,
                updated_at=str(item.get("server_mtime") or ""),
            ))
        return files

    # ---------- 转存 + 取直链 ----------
    async def _ensure_dir(self, path: str):
        bdstoken = await self._get_bdstoken()
        body = f"path={quote(path, safe='')}&isdir=1&size&block_list=%5B%5D&method=post&dataType=json"
        url = (f"https://pan.baidu.com/api/create?a=commit&channel=chunlei&web=1"
               f"&app_id={APP_ID}&clienttype=0&bdstoken={bdstoken}")
        try:
            await self._client.post(url, content=body, headers=self._headers({
                "User-Agent": UA_NETDISK,
                "Referer": "https://yun.baidu.com/disk/main",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }))
        except Exception:
            pass  # 目录已存在会失败，忽略

    async def _transfer(self, session: ShareSession, file: ShareFile) -> dict:
        bdstoken = await self._get_bdstoken()
        share_id = session.raw.get("share_id") or ""
        uk = session.raw.get("uk") or ""
        sekey = session.raw.get("sekey") or ""
        await self._ensure_dir(TEMP_DIR)
        url = (f"https://pan.baidu.com/share/transfer?shareid={share_id}&from={uk}"
               f"&channel=chunlei&sekey={sekey}&ondup=newcopy&web=1&app_id={APP_ID}"
               f"&bdstoken={bdstoken}&clienttype=0")
        body = f"fsidlist=%5B%22{file.fid}%22%5D&path={quote(TEMP_DIR, safe='')}"
        headers = {
            "Origin": "https://pan.baidu.com", "Referer": "https://pan.baidu.com/s/",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Cookie": self._auth_cookie(sekey),
        }
        resp = await self._client.post(url, content=body, headers=headers)
        data = resp.json()
        errno = int(data.get("errno", 0))
        if errno != 0:
            raise PanError(data.get("errmsg") or f"转存失败（errno={errno}）")
        lst = ((data.get("extra") or {}).get("list") or [])
        first = lst[0] if lst else {}
        fs_id_new = str(first.get("to_fs_id") or "")
        path_new = str(first.get("to") or f"{TEMP_DIR}/")
        if not fs_id_new:
            raise PanError("转存失败：未返回新文件")
        return {"fs_id": fs_id_new, "path": path_new}

    async def _locate_download(self, path: str) -> str:
        import time
        ts = int(time.time())
        url = (f"https://d.pcs.baidu.com/rest/2.0/pcs/file?method=locatedownload"
               f"&app_id={APP_ID}&clienttype=17&ver=4.0&ant=1&check_blue=1&es=1&esl=1"
               f"&apn_id=1_-1&freeisp=0&queryfree=0&use=1&dtype=1&eck=1&ehps=1"
               f"&err_ver=1.0&network_type=WIFI&channel=0&path={quote(path, safe='')}"
               f"&time={ts}&rand=5ed606e9da222cde0474cdf70eda884b"
               f"&devuid=0F1E9FC2E084472DA5A61C4CF4C759AF"
               f"&cuid=0F1E9FC2E084472DA5A61C4CF4C759AF&deviceid=348642637967375013"
               f"&psign=860a071f77c860e8cea06e4e54c518f3&version=2.2.111.34&version_app=12.24.6&vip=0")
        headers = {"User-Agent": UA_NETDISK, "Content-Type": "application/x-www-form-urlencoded"}
        resp = await self._client.post(url, content="0", headers=self._headers(headers))
        data = resp.json()
        if int(data.get("errno", 0)) != 0:
            raise PanError(data.get("errmsg") or "获取高速下载链接失败")
        urls = data.get("urls") or []
        candidates = [u for u in urls if u.get("url")]
        # 优先 encrypt=0 明文通道（appall*），排除 rank1 的 d2-ant 加密通道（需 AES-CTR 解密）
        plain = [u for u in candidates if int(u.get("encrypt", 1)) == 0]
        plain.sort(key=lambda u: not str(u.get("url", "")).startswith("https"))
        chosen = (plain[0] if plain else
                  next((u for u in candidates if str(u.get("url", "")).startswith("https")), None) or
                  (candidates[0] if candidates else None))
        if not chosen:
            raise PanError("未返回下载链接")
        return chosen["url"]

    async def get_share_download_link(self, session: ShareSession, file: ShareFile) -> DownloadLink:
        tr = await self._transfer(session, file)
        url = await self._locate_download(tr["path"])
        return DownloadLink(
            fid=tr["fs_id"], filename=file.fname, url=url, size=file.fsize,
            headers={"User-Agent": UA_NETDISK, "Referer": "https://pan.baidu.com/",
                     "Cookie": self.cookie},
        )
