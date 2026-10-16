"""蓝奏云客户端（移植 YunX LanzouApi 协议，Python/httpx 重写）。

分享链路（匿名，HTML 抓取 + JS 变量）：
分享页 → (iframe 下载页) → downprocess 取 dom/url → /file/<rel> 探测跳转
→ 遇验证页走 ajax.php / acw_sc__v2 Cookie。
个人盘：task=22 先生成分享链接再走匿名链路（蓝奏无个人盘直链接口）。
"""
import re
from urllib.parse import urljoin, urlparse

from ..base import PanClient
from ..models import DownloadLink, PanError, ShareFile, ShareSession

WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
MAX_FOLDER_PAGES = 50
POS = [15, 35, 29, 24, 33, 16, 1, 38, 10, 9, 19, 31, 40, 27, 22, 23, 25, 13, 6, 11,
       39, 18, 20, 8, 14, 21, 32, 26, 2, 30, 7, 4, 17, 5, 3, 28, 34, 37, 12, 36]
ACW_MASK = "3000176000856006061501533003690027800375"


def _acw_sc_v2(arg1: str) -> str:
    q = [""] * 40
    for z in range(40):
        target = POS[z]
        q[z] = arg1[target - 1] if 0 < target <= len(arg1) else "0"
    reordered = "".join(q)
    out = []
    for i in range(0, len(reordered), 2):
        a = int(reordered[i:i + 2], 16)
        b = int(ACW_MASK[i:i + 2], 16)
        out.append(f"{a ^ b:02x}")
    return "".join(out)


def _js_var(html: str, name: str) -> str | None:
    m = re.search(rf"(?:(?:var|let|const)\s+)?{name}\s*=\s*['\"]([^'\"]*)['\"]", html)
    return m.group(1) if m else None


def _js_var_raw(html: str, name: str) -> str | None:
    m = re.search(rf"(?:var|let|const)\s+{name}\s*=\s*([^;,\n\r]+)", html)
    return m.group(1).strip().strip("'\"") if m else None


def _input_value(html: str, name: str) -> str | None:
    m = (re.search(rf"<input[^>]*name=['\"]{name}['\"][^>]*value=['\"]([^'\"]*)['\"]", html)
         or re.search(rf"<input[^>]*value=['\"]([^'\"]*)['\"][^>]*name=['\"]{name}['\"]", html))
    return m.group(1) if m else None


def _parse_display_size(text: str) -> int:
    m = re.search(r"([\d.]+)\s*([KMGT]?)", text or "", re.I)
    if not m:
        return 0
    val = float(m.group(1))
    factor = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}.get(m.group(2).upper(), 1)
    return int(val * factor)


class LanzouClient(PanClient):
    platform = "lanzou"
    label = "蓝奏云"
    REQUIRED_COOKIES = ()
    GUEST_SUPPORTED = True
    GUEST_MAX_BYTES = 0

    def api_user_agent(self) -> str:
        return WEB_UA

    def _headers(self, referer: str, origin: str, cookie: str = "") -> dict:
        h = {"User-Agent": WEB_UA, "Referer": referer, "Origin": origin,
             "X-Requested-With": "XMLHttpRequest"}
        if cookie:
            h["Cookie"] = cookie
        return h

    async def fetch_nickname(self) -> str:
        return ""

    async def refresh_session(self):
        pass

    async def _get_text(self, url: str, referer: str = "") -> str:
        self._ensure_proxy()
        h = {"User-Agent": WEB_UA}
        if referer:
            h["Referer"] = referer
        resp = await self._client.get(url, headers=h)
        if resp.status_code in (401, 403):
            raise PanError("蓝奏访问被拒绝，请稍后重试或在分享页完成验证")
        if resp.status_code == 429:
            raise PanError("蓝奏请求过于频繁，请稍后再试")
        return resp.text

    async def create_session(self, share_id: str, passcode: str = "") -> ShareSession:
        # 蓝奏分享 URL 形如 https://<host>/<id>；share_id 即路径尾段
        return ShareSession(platform=self.platform, share_id=share_id, passcode=passcode or "")

    def _share_url(self, session: ShareSession) -> str:
        if session.share_id.startswith("http"):
            return session.share_id
        # 默认蓝奏主域
        return f"https://wwa.lanzoui.com/{session.share_id.lstrip('/')}"

    async def list_share_files(self, session: ShareSession, pdir_fid: str = "",
                               page: int = 1, size: int = 100) -> list[ShareFile]:
        share_url = self._share_url(session)
        html = await self._get_text(share_url)
        if "请输入密码" in html or 'id="pwbox"' in html or "input_password" in html:
            if not session.passcode:
                raise PanError("该分享需要提取码")
        is_folder = ("filemoreajax" in html or 'class="filemore"' in html or "file_more" in html)
        title = self._extract_title(html)
        if not session.title:
            session.title = title
        if not is_folder:
            # 单文件分享：必须真的从页面解析到文件信息，否则视为抓取失败（避免把错误页伪装成文件）
            fid = (_js_var(html, "file") or
                   (re.search(r"(?:ajaxm|ajaxfile)\.php\?file=(\d+)", html) or [None, None])[1])
            size = self._display_size(html)
            if not title or (not fid and not size and "取消" not in html and "不存在" not in html):
                if "取消" in html or "不存在" in html:
                    raise PanError("蓝奏文件已取消分享或不存在")
                raise PanError("蓝奏解析失败：未能从分享页提取文件信息（链接可能已失效或需要提取码）")
            return [ShareFile(fid=str(fid or session.share_id), fname=title,
                              fsize=size, isdir=False)]
        # 文件夹：filemoreajax 分页
        lx, fid, t, k = _js_var(html, "lx"), _js_var(html, "fid"), _js_var(html, "t"), _js_var(html, "k")
        if not (lx and t and k):
            raise PanError("蓝奏分享分页参数异常，请重试")
        origin = f"{urlparse(share_url).scheme}://{urlparse(share_url).netloc}"
        files: list[ShareFile] = []
        seen = set()
        pg = 1
        while pg <= MAX_FOLDER_PAGES:
            fields = {"lx": lx, "fid": fid or "", "t": t, "k": k,
                      "pwd": session.passcode or "", "pg": str(pg)}
            data = await self._form_post(f"{origin}/filemoreajax.php", fields, share_url, origin)
            zt = int(data.get("zt") or 0) if isinstance(data, dict) else 0
            if zt == 2:
                break
            if zt == 3:
                raise PanError("蓝奏提取码错误，请检查后重新解析")
            if zt == 4:
                pg -= 1
                if pg <= 0:
                    raise PanError("蓝奏请求过于频繁，请稍后再试")
                pg += 1
                continue
            if zt != 1:
                raise PanError("蓝奏解析失败，请确认分享链接和提取码后重试")
            arr = data.get("text") or []
            if not arr:
                break
            for item in arr:
                iid = str(item.get("id") or "")
                if not iid or iid in seen:
                    continue
                seen.add(iid)
                files.append(ShareFile(
                    fid=iid, fname=str(item.get("name_all") or item.get("name") or ""),
                    fsize=_parse_display_size(str(item.get("size") or "")), isdir=False,
                    updated_at=str(item.get("time") or ""),
                ))
            pg += 1
        return files

    async def _form_post(self, url: str, fields: dict, referer: str, origin: str) -> dict:
        self._ensure_proxy()
        resp = await self._client.post(url, data=fields, headers=self._headers(referer, origin))
        text = resp.text
        if resp.status_code == 429:
            raise PanError("蓝奏请求过于频繁，请稍后再试")
        try:
            return resp.json()
        except Exception:
            if text.lstrip().startswith("<"):
                raise PanError("蓝奏返回了验证页面，请稍后重试")
            raise PanError("蓝奏解析服务响应异常，请稍后重试")

    def _extract_title(self, html: str) -> str:
        m = re.search(r"<title>([^<]*)</title>", html)
        if m:
            clean = m.group(1).replace(" - 蓝奏云", "").replace("蓝奏云", "").strip()
            if clean and "密码" not in clean:
                return clean
        m = re.search(r'class=["\']n["\']>([^<]+)<', html)
        if m:
            return m.group(1).strip()
        m = re.search(r"var\s+filename\s*=\s*['\"]([^'\"]+)['\"]", html)
        return m.group(1) if m else ""

    def _display_size(self, html: str) -> int:
        m = re.search(r"(?:文件大小|大小)\s*[:：]\s*([\d.]+)\s*([KMGT]?)(?:i?B)?", html, re.I)
        return _parse_display_size(f"{m.group(1)} {m.group(2)}") if m else 0

    async def get_share_download_link(self, session: ShareSession, file: ShareFile) -> DownloadLink:
        share_url = self._share_url(session)
        origin = f"{urlparse(share_url).scheme}://{urlparse(share_url).netloc}"
        html = await self._get_text(share_url)
        # A2：同源 iframe 下载页
        m = re.search(r"<iframe[^>]+src=[\"']([^\"']+)[\"']", html)
        if m:
            iframe = urljoin(origin, m.group(1))
            if urlparse(iframe).netloc == urlparse(share_url).netloc:
                html = await self._get_text(iframe, share_url)
        fid = (re.search(r"(?:ajaxm|ajaxfile)\.php\?file=(\d+)", html) or [None, file.fid])[1] \
            or file.fid or session.share_id
        with_pwd = bool(session.passcode)
        ajax_url = self._resolve_ajax_url(html, origin, fid, with_pwd)
        sign = _js_var(html, "wp_sign") or _js_var(html, "sign") or _input_value(html, "sign")
        if not sign:
            raise PanError("蓝奏分享页缺少下载参数，请重新解析")
        fields = {"action": "downprocess", "sign": sign}
        if with_pwd:
            fields["p"] = session.passcode
            fields["kd"] = "1"
        else:
            key = _js_var(html, "ajaxdata") or _js_var(html, "websignkey") or _input_value(html, "websignkey") or ""
            fields["signs"] = _js_var(html, "signs") or key
            fields["websignkey"] = key
            fields["websign"] = _js_var(html, "websign") or ""
            fields["kd"] = _js_var_raw(html, "kdns") or "1"
            fields["ves"] = "1"
        data = await self._form_post(ajax_url, fields, share_url, origin)
        zt = int(data.get("zt") or 0)
        if zt != 1:
            inf = str(data.get("inf") or "")
            if "密码" in inf or "提取码" in inf:
                raise PanError("蓝奏提取码错误，请检查后重新解析")
            if any(w in inf for w in ("频繁", "次数", "稍后")):
                raise PanError("蓝奏请求过于频繁，请稍后再试")
            raise PanError("蓝奏解析失败，请确认分享链接和提取码后重试")
        dom = str(data.get("dom") or "")
        rel = str(data.get("url") or "")
        if not dom or not rel or rel.startswith("/") or "://" in rel:
            raise PanError("蓝奏解析失败，请确认分享链接和提取码后重试")
        jump = f"{urlparse(dom).scheme}://{urlparse(dom).netloc}/file/{rel}"
        final_url, size = await self._probe_and_verify(jump, origin)
        return DownloadLink(
            fid=file.fid, filename=file.fname or str(data.get("inf") or ""),
            url=final_url, size=size or file.fsize,
            headers={"User-Agent": WEB_UA, "Referer": f"{origin}/", "Cookie": "down_ip=1"},
        )

    def _resolve_ajax_url(self, html: str, origin: str, file_id: str, with_pwd: bool) -> str:
        cand = _js_var(html, "domain1") or _js_var(html, "domain2")
        if cand and "/ajax" in cand:
            return cand
        m = re.search(r"https?://[^'\"\s]+/(?:ajaxm|ajaxfile)\.php\?file=\d+", html)
        if m:
            return m.group(0)
        return f"{origin}/ajaxfile.php?file={file_id}" if with_pwd else f"{origin}/ajaxm.php?file={file_id}"

    async def _probe_and_verify(self, jump: str, share_origin: str) -> tuple[str, int]:
        url = jump
        for _ in range(8):
            host = urlparse(url).netloc
            origin = f"{urlparse(url).scheme}://{host}"
            self._ensure_proxy()
            resp = await self._client.head(url, headers={
                "User-Agent": WEB_UA, "Referer": f"{share_origin}/", "Cookie": "down_ip=1"})
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("location")
                if not loc:
                    raise PanError("蓝奏下载地址异常，请稍后重试")
                url = urljoin(url, loc)
                continue
            if 200 <= resp.status_code < 300:
                ctype = resp.headers.get("content-type", "")
                if "text/html" in ctype:
                    page = await self._get_text(url, f"{share_origin}/")
                    if "arg1" in page and "acw_sc__v2" not in page:
                        raise PanError("蓝奏访问验证未通过，请稍后重试")
                    if "验证并下载" in page:
                        new_url = await self._submit_verify(page, origin, share_origin)
                        if new_url:
                            url = new_url
                            continue
                        raise PanError("蓝奏需要进一步验证，请稍后重试")
                    raise PanError("蓝奏返回的是验证页面，未创建下载任务")
                size = self._size_from_headers(resp.headers)
                return url, size
            if resp.status_code in (403, 404, 410):
                raise PanError("蓝奏下载地址已失效，请重新解析")
            if resp.status_code == 429:
                raise PanError("蓝奏请求过于频繁，请稍后再试")
            raise PanError(f"蓝奏下载地址异常（HTTP {resp.status_code}）")
        raise PanError("蓝奏下载跳转次数过多，请稍后重试")

    @staticmethod
    def _size_from_headers(headers) -> int:
        cr = headers.get("content-range") or ""
        if "/" in cr:
            try:
                return int(cr.rsplit("/", 1)[1])
            except ValueError:
                pass
        cl = headers.get("content-length")
        return int(cl) if cl and cl.isdigit() else 0

    async def _submit_verify(self, html: str, node_origin: str, share_origin: str) -> str | None:
        m = re.search(r"data\s*:\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", html, re.S)
        file_v = sign_v = None
        if m:
            fm = re.search(r"['\"]?file['\"]?\s*:\s*['\"]([^'\"]+)['\"]", m.group(1))
            sm = re.search(r"['\"]?sign['\"]?\s*:\s*['\"]([^'\"]+)['\"]", m.group(1))
            file_v = fm.group(1) if fm else None
            sign_v = sm.group(1) if sm else None
        if not file_v:
            file_v = _input_value(html, "file")
        if not file_v or not sign_v:
            return None
        import asyncio
        await asyncio.sleep(2.0)
        data = await self._form_post(f"{node_origin}/ajax.php",
                                     {"file": file_v, "el": "2", "sign": sign_v},
                                     f"{share_origin}/", node_origin)
        if int(data.get("zt") or 0) == 1 and data.get("url"):
            u = str(data["url"])
            if u == "?SignError":
                raise PanError("蓝奏验证已过期，请重新解析")
            return u if u.startswith("http") else f"{node_origin}/file/{u}"
        return None
