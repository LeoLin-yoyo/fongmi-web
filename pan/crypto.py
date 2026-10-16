"""网盘凭证加密：AES-256-GCM，密钥文件 data/.secret/pan.key（0600 权限）。

移植 YunX CredentialCipher 的口径：密文带上下文前缀（防跨上下文密文挪用），
落库前加密、读出时解密；密钥文件丢失则密文不可恢复。
依赖复用项目已有的 pycryptodome。
"""
import base64
import os
import secrets

from Crypto.Cipher import AES

from spider.proxy_config import _CONFIG_PATH  # 同目录数据区

_KEY_DIR = os.path.join(os.path.dirname(_CONFIG_PATH), ".secret")
_KEY_FILE = os.path.join(_KEY_DIR, "pan.key")
_PREFIX = "gcm1:"


def _load_key() -> bytes:
    os.makedirs(_KEY_DIR, exist_ok=True)
    if os.path.isfile(_KEY_FILE):
        with open(_KEY_FILE, "rb") as f:
            key = f.read()
        if len(key) == 32:
            return key
    key = secrets.token_bytes(32)
    fd = os.open(_KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    return key


def encrypt(plaintext: str, context: str = "pan.cookie") -> str:
    if not plaintext:
        return ""
    nonce = secrets.token_bytes(12)
    cipher = AES.new(_load_key(), AES.MODE_GCM, nonce=nonce)
    cipher.update(context.encode("utf-8"))  # AAD：上下文绑定
    ct, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))
    return _PREFIX + base64.b64encode(nonce + tag + ct).decode("ascii")


def decrypt(ciphertext: str, context: str = "pan.cookie") -> str:
    if not ciphertext or not ciphertext.startswith(_PREFIX):
        return ciphertext  # 兼容早期明文存量
    raw = base64.b64decode(ciphertext[len(_PREFIX):])
    nonce, tag, ct = raw[:12], raw[12:28], raw[28:]
    cipher = AES.new(_load_key(), AES.MODE_GCM, nonce=nonce)
    cipher.update(context.encode("utf-8"))
    return cipher.decrypt_and_verify(ct, tag).decode("utf-8")
