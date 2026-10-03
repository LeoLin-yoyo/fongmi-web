"""同步 HTTP 抓取助手：SSRF 校验 + httpx 实现

替代散落各处的 urllib.request.urlopen 动态调用：
- 统一先过 ensure_http_url（协议白名单 + 解析后阻断私网/环回/保留地址）
- TLS 沿用本项目既定决策（源站证书普遍不规范，见安全决策 HI-02~06），
  与 urllib 时代各文件自建的 _SSL_CTX(CERT_NONE) 行为一致
"""
import ssl

import httpx

from spider.net import ensure_http_url


def _tls_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def http_get_sync(url: str, timeout: float = 10, headers: dict | None = None) -> str:
    """GET 文本内容；SSRF 校验失败或网络错误向上抛出，由调用方按需兜底"""
    url = ensure_http_url(url)
    with httpx.Client(timeout=timeout, follow_redirects=True, verify=_tls_ctx()) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.text


def http_post_json_sync(url: str, payload, timeout: float = 30) -> dict:
    """POST JSON 并解析响应（用于硬编码本机地址的 Node 引擎通道）"""
    import json as _json
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, content=_json.dumps(payload).encode(),
                           headers={"Content-Type": "application/json"})
        return resp.json()
