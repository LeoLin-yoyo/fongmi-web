"""139 网盘（和彩云）客户端（移植 YunX C139Api 协议，Python/httpx 重写）。

分享接口（IOutLink 系）请求/响应 AES-CBC 加密（固定密钥），匿名可列目录；
dlFromOutLinkV3 取直链（OBS 预签名 900s）。管理接口明文 JSON + mcloud-sign。
"""
import base64
import gzip
import hashlib
import json
import random
import string
import time
from datetime import datetime
from urllib.parse import quote

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from ..base import PanClient
from ..models import DownloadLink, PanError, ShareFile, ShareSession

SHARE_BASE = "https://share-kd-njs.yun.139.com"
CLOUD_BASE = "https://personal-kd-njs.yun.139.com"
AES_KEY = b"PVGDwmcvfs1uV3d1"  # 16B 固定
SHARE_DEVID = "||3|12.27.0|||||chrome 150.0.0.0|360X444|zh-cn|||"
SHARE_CHANNEL = "10245500"
SHARE_MM_SOURCE = "0002"
SHARE_UA = ("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36")
PC_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _aes_encrypt(plaintext: str) -> str:
    iv = bytes(random.getrandbits(8) for _ in range(16))
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
    ct = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
    return base64.b64encode(iv + ct).decode("ascii")


def _aes_decrypt(b64: str) -> str:
    raw = base64.b64decode(b64)
    iv, ct = raw[:16], raw[16:]
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
    out = unpad(cipher.decrypt(ct), AES.block_size)
    if out[:2] == b"\x1f\x8b":  # gzip 魔数
        out = gzip.decompress(out)
    return out.decode("utf-8")


def _mcloud_sign(body_json: str) -> str:
    """按明文 body 计算 mcloud-sign：encodeURIComponent→字符升序→base64→两段 md5→大写 md5。"""
    encoded = quote(body_json, safe=":@/")
    # 还原 JS encodeURIComponent 不转义、而 urllib 会转义的字符
    for a, b in (("%21", "!"), ("%27", "'"), ("%28", "("), ("%29", ")"), ("%2A", "*"),
                 ("%7E", "~")):
        encoded = encoded.replace(a, b)
    sorted_str = "".join(sorted(encoded))
    b64 = base64.b64encode(sorted_str.encode("utf-8")).decode("ascii")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rnd = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(16))
    res = hashlib.md5(b64.encode()).hexdigest() + hashlib.md5(f"{ts}:{rnd}".encode()).hexdigest()
    sign = hashlib.md5(res.encode()).hexdigest().upper()
    return f"{ts},{rnd},{sign}"


class C139Client(PanClient):
    platform = "c139"
    label = "139网盘"
    REQUIRED_COOKIES = ()  # 分享接口匿名，管理接口需 authorization
    GUEST_SUPPORTED = True
    GUEST_MAX_BYTES = 0

    def api_user_agent(self) -> str:
        return SHARE_UA

    def _extract_account(self) -> str:
        m = __import__("re").search(r"authorization=([^;]+)", self.cookie or "")
        if not m:
            return ""
        try:
            val = m.group(1).strip()
            raw = base64.b64decode(val.replace("Basic ", ""))
            parts = raw.decode("utf-8", "replace").split(":")
            if len(parts) >= 2:
                return parts[1]
        except Exception:
            pass
        return ""

    @classmethod
    def is_valid_cookie(cls, cookie: str) -> bool:
        if not cookie:
            return False
        return "authorization=" in cookie or ("Os_SSo_Sid=" in cookie and "RMKEY=" in cookie)

    # ---------- 分享接口（AES 加密） ----------
    async def _share_post(self, path: str, plain_body: dict) -> dict:
        body_json = json.dumps(plain_body, ensure_ascii=False, separators=(",", ":"))
        encrypted = _aes_encrypt(body_json)
        headers = {
            "hcy-cool-flag": "1",
            "x-deviceinfo": SHARE_DEVID,
            "x-huawei-channelsrc": SHARE_CHANNEL,
            "x-mm-source": SHARE_MM_SOURCE,
            "Content-Type": "application/json;charset=UTF-8",
            "User-Agent": SHARE_UA,
            "Origin": "https://yun.139.com",
            "Referer": "https://yun.139.com/",
            "Accept": "application/json, text/plain, */*",
        }
        self._ensure_proxy()
        resp = await self._client.post(f"{SHARE_BASE}{path}", content=encrypted, headers=headers)
        text = resp.text.strip()
        # 响应通常为 AES-CBC base64 密文；也兼容网关透传的明文 JSON
        if text.startswith("{"):
            try:
                return json.loads(text)
            except ValueError:
                pass
        try:
            return json.loads(_aes_decrypt(text))
        except Exception:
            raise PanError(f"139 响应解析失败（HTTP {resp.status_code}）")

    # ---------- 账号 ----------
    async def fetch_nickname(self) -> str:
        return self._extract_account()

    async def refresh_session(self):
        pass

    # ---------- 分享解析 ----------
    async def create_session(self, share_id: str, passcode: str = "") -> ShareSession:
        body = {"getOutLinkGeneralReq": {"linkID": share_id, "isPasswd": 1, "account": ""}}
        data = await self._share_post("/yun-share/richlifeApp/devapp/IOutLink/getOutLinkGeneral", body)
        title, pwd = "", passcode
        try:
            general = ((data.get("data") or {}).get("getOutLinkGeneralResp") or {}).get("outLinkGeneral") or []
            if general:
                title = general[0].get("lkName") or ""
                if not pwd:
                    pwd = general[0].get("passwd") or ""
        except Exception:
            pass
        return ShareSession(platform=self.platform, share_id=share_id,
                            passcode=pwd or "", title=title)

    async def list_share_files(self, session: ShareSession, pdir_fid: str = "root",
                               page: int = 1, size: int = 200) -> list[ShareFile]:
        p_ca_id = pdir_fid if pdir_fid and pdir_fid != "0" else "root"
        body = {"getOutLinkInfoReq": {
            "account": "", "linkID": session.share_id, "passwd": session.passcode or "",
            "caSrt": 1, "coSrt": 1, "srtDr": 0,
            "bNum": (page - 1) * size + 1, "pCaID": p_ca_id, "eNum": page * size,
        }}
        data = await self._share_post("/yun-share/richlifeApp/devapp/IOutLink/getOutLinkInfoV6", body)
        if str(data.get("resultCode") or "") not in ("0", ""):
            code = str(data.get("resultCode"))
            if code == "9188":
                raise PanError("139 提取码错误")
            raise PanError(data.get("resultDesc") or f"139 列目录失败（resultCode={code}）")
        d = data.get("data") or {}
        files = []
        for ca in d.get("caLst") or []:  # 子文件夹
            files.append(ShareFile(
                fid=str(ca.get("caID") or ""), fname=str(ca.get("caName") or ""),
                fsize=0, isdir=True, pdir_fid=p_ca_id, updated_at=str(ca.get("udTime") or ""),
            ))
        for co in d.get("coLst") or []:  # 文件
            files.append(ShareFile(
                fid=str(co.get("coID") or ""), fname=str(co.get("coName") or ""),
                fsize=int(co.get("coSize") or 0), isdir=False, pdir_fid=p_ca_id,
                updated_at=str(co.get("udTime") or ""),
            ))
        return files

    # ---------- 取直链 ----------
    async def get_share_download_link(self, session: ShareSession, file: ShareFile) -> DownloadLink:
        account = self._extract_account()
        body = {"dlFromOutLinkReqV3": {
            "account": account, "linkID": session.share_id,
            "coIDLst": {"item": [file.fid]},
            "commonAccountInfo": {"account": account, "accountType": 1},
        }}
        data = await self._share_post("/yun-share/richlifeApp/devapp/IOutLink/dlFromOutLinkV3", body)
        if str(data.get("resultCode") or "") not in ("0", ""):
            raise PanError(data.get("resultDesc") or "139 获取下载链接失败")
        d = data.get("data") or {}
        url = d.get("redrUrl") or ""
        if not url:
            raise PanError("未返回下载链接")
        return DownloadLink(
            fid=file.fid, filename=str(d.get("fileName") or file.fname),
            url=url, size=int(d.get("coSize") or d.get("size") or file.fsize),
            headers={"User-Agent": PC_UA, "Referer": "https://yun.139.com/"},
        )
