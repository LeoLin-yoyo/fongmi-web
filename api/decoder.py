"""FongMi 配置解密模块
支持：明文 JSON / Base64 编码 / AES-CBC 加密（hex 编码）
"""

import base64
import re
from Crypto.Cipher import AES


def decrypt_config(raw_data: str) -> str:
    """自动检测并解密配置数据"""
    raw_data = raw_data.strip()
    if not raw_data:
        raise ValueError("配置数据为空")

    # 移除 UTF-8 BOM
    if raw_data.startswith("\ufeff"):
        raw_data = raw_data[1:].strip()

    # 已经是 JSON
    if raw_data.startswith("{") or raw_data.startswith("["):
        return raw_data

    # 包含 ** → Base64
    if "**" in raw_data:
        raw_data = _base64_decode(raw_data)

    # 以 2423 开头 → AES-CBC 加密（hex 编码）
    if raw_data.startswith("2423"):
        raw_data = _cbc_decrypt(raw_data)

    return raw_data


def _cbc_decrypt(hex_data: str) -> str:
    """AES-CBC 解密 FongMi 加密配置"""
    hex_data = re.sub(r"\s+", "", hex_data)

    # hex → bytes → string (lowercase)
    try:
        decoded_str = bytes.fromhex(hex_data).decode("utf-8", errors="ignore").lower()
    except Exception:
        decoded_str = ""

    # 提取 key：$# 到 #$ 之间
    key_start = decoded_str.find("$#")
    key_end = decoded_str.find("#$")
    if key_start == -1 or key_end == -1 or key_start >= key_end:
        raise ValueError("无法提取解密密钥")
    key = _pad_end(decoded_str[key_start + 2 : key_end])

    # 提取 iv：最后 13 个字符
    iv = _pad_end(decoded_str[-13:])

    # 密文：从 "2324" 后开始，到倒数 26 字符前结束
    cipher_start = hex_data.find("2324")
    if cipher_start == -1:
        raise ValueError("无法定位密文起始位置")
    cipher_hex = hex_data[cipher_start + 4 : len(hex_data) - 26]

    # AES/CBC/PKCS5 解密
    cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
    decrypted = cipher.decrypt(bytes.fromhex(cipher_hex))

    # 去除 PKCS5 填充
    pad_len = decrypted[-1]
    if isinstance(pad_len, int) and 0 < pad_len <= 16:
        decrypted = decrypted[:-pad_len]
    return decrypted.decode("utf-8")


def _base64_decode(data: str) -> str:
    """从 ** 标记后提取 Base64 内容并解码（自动填充缺失的 =）"""
    match = re.search(r"[A-Za-z0-9]{8}\*\*", data)
    if not match:
        return data
    b64_part = data[match.end() :]
    # 修复 Base64 填充：长度必须是 4 的倍数
    remainder = len(b64_part) % 4
    if remainder:
        b64_part += "=" * (4 - remainder)
    return base64.b64decode(b64_part).decode("utf-8")


def _pad_end(key: str) -> str:
    """padEnd 到 16 字节"""
    return key + "0000000000000000"[len(key) :]


def fix_js_path(url: str, data: str) -> str:
    """修复 JS 爬虫中的相对路径"""
    pattern = re.compile(r'"(\.|\\.\\.)/(.?|.+?)\\\.js\?(.?|.+?)"')

    def replacer(match):
        base = url.rsplit("/", 1)[0] if url else ""
        path = match.group(0)
        path = path.replace('\\.', '.').replace('\\?', '?')
        return f'"{base}/{path[1:-1]}"'

    return pattern.sub(replacer, data)
