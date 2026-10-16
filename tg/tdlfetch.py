"""tdl 二进制自动下载（移植 tdl-web lib/tdlfetch.js 口径）。

安全：仅 https + 主机白名单 {api.github.com, github.com, objects.githubusercontent.com,
codeload.github.com, release-assets.githubusercontent.com}；每跳重定向重新校验；
DNS 解析出的所有地址必须是公网单播。
"""
import asyncio
import os
import platform
import shutil
import tarfile
import zipfile
from loguru import logger

from spider.net import ensure_http_url

RELEASE_API = "https://api.github.com/repos/iyear/tdl/releases/latest"
ALLOWED_HOSTS = {
    "api.github.com", "github.com", "objects.githubusercontent.com",
    "codeload.github.com", "release-assets.githubusercontent.com",
}
MAX_BYTES = 200 * 1024 * 1024


def target_dir() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "tdl")


def target_asset_suffix() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "64bit"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    elif machine in ("armv7l", "armv7"):
        arch = "armv7"
    elif machine in ("i386", "i686", "x86"):
        arch = "32bit"
    else:
        arch = "64bit"
    if system == "Windows":
        return f"tdl_Windows_{arch}.zip"
    if system == "Darwin":
        return f"tdl_MacOS_{arch}.tar.gz"
    return f"tdl_Linux_{arch}.tar.gz"


def _validate_url(url: str):
    """每跳重定向后的 URL 都重新校验（协议 + 白名单 + 公网地址）。"""
    from urllib.parse import urlparse
    p = urlparse(url)
    if p.scheme != "https":
        raise ValueError(f"仅允许 https 下载: {url[:80]}")
    if p.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"不在下载白名单的主机: {p.hostname}")
    ensure_http_url(url)  # 私网/环回阻断


async def _fetch_latest_asset() -> dict:
    import httpx
    _validate_url(RELEASE_API)
    suffix = target_asset_suffix()
    async with httpx.AsyncClient(follow_redirects=False, timeout=30, verify=False) as client:
        resp = await client.get(RELEASE_API, headers={"User-Agent": "fongmi-web"})
        resp.raise_for_status()
        release = resp.json()
    for asset in release.get("assets", []):
        if asset.get("name") == suffix:
            return {"url": asset["browser_download_url"], "name": suffix,
                    "tag": release.get("tag_name", "")}
    raise ValueError(f"未找到匹配的 tdl 资源: {suffix}")


async def download_latest(on_progress=None) -> dict:
    """从 GitHub Releases 下载并解压 tdl 到 <root>/tdl/。"""
    import httpx
    asset = await _fetch_latest_asset()
    url = asset["url"]
    out_dir = target_dir()
    os.makedirs(out_dir, exist_ok=True)
    archive = os.path.join(out_dir, asset["name"])

    # 下载（手动跟随重定向，每跳校验）
    total = 0
    async with httpx.AsyncClient(follow_redirects=False, timeout=httpx.Timeout(60, read=300),
                                 verify=False) as client:
        cur = url
        for _ in range(6):
            _validate_url(cur)
            async with client.stream("GET", cur, headers={"User-Agent": "fongmi-web"}) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    loc = r.headers.get("location")
                    if not loc:
                        raise ValueError("重定向缺少 Location")
                    from urllib.parse import urljoin
                    cur = urljoin(cur, loc)
                    continue
                r.raise_for_status()
                with open(archive, "wb") as f:
                    async for chunk in r.aiter_bytes(256 * 1024):
                        total += len(chunk)
                        if total > MAX_BYTES:
                            raise ValueError("下载体积超过上限（200MB）")
                        f.write(chunk)
                        if on_progress:
                            on_progress(total)
                break
        else:
            raise ValueError("重定向次数过多")

    # 解压
    exe = _extract(archive, out_dir, asset["name"])
    try:
        os.unlink(archive)
    except OSError:
        pass
    if exe and os.name != "nt":
        os.chmod(exe, 0o755)
    return {"path": exe, "tag": asset["tag"], "size": total}


def _extract(archive: str, out_dir: str, name: str) -> str:
    exe_name = "tdl.exe" if os.name == "nt" else "tdl"
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(out_dir)
    else:
        with tarfile.open(archive, "r:gz") as t:
            t.extractall(out_dir)
    # 找解压出的可执行文件（可能在子目录）
    for root, _dirs, files in os.walk(out_dir):
        for fn in files:
            if fn in (exe_name, "tdl", "tdl.exe"):
                return os.path.join(root, fn)
    return ""


def status() -> dict:
    from tg.config import get_config
    from tg.runner import runner
    out = target_dir()
    return {"autoDir": out, "target": target_asset_suffix(),
            "hasTdl": bool(runner.locate(get_config().tdl_path))}
