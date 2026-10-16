"""115 电脑端私有协议：RSA(1024) + XOR 变换（移植 YunX Pan115Crypto）。

用于 proapi.115.com/app/chrome/downurl（大文件必须走该加密接口）。
- 请求：newKey(16B) + symmetricEncode(body, key)，再 RSA 公钥加密整段 → base64
- 响应：base64 → RSA 解密 → salt(16B) + body，再 symmetricDecode
"""
import base64
import os
import random

MODULUS = int(
    "8686980c0f5a24c4b9d43020cd2c22703ff3f450756529058b1cf88f09b86021"
    "36477198a6e2683149659bd122c33592fdb5ad47944ad1ea4d36c6b172aad633"
    "8c3bb6ac6227502d010993ac967d1aef00f0c8e038de2e4d3bc2ec368af2e9f1"
    "0a6f1eda4f7262f136420c07c331b871bf139f74f3010e3c4fe57df3afb71683", 16)
EXPONENT = 0x10001
RSA_BLOCK = 128
RSA_PLAIN_CHUNK = 117  # 128 - 11

KEY_TABLE = bytes([
    0xf0, 0xe5, 0x69, 0xae, 0xbf, 0xdc, 0xbf, 0x8a, 0x1a, 0x45, 0xe8, 0xbe, 0x7d, 0xa6, 0x73, 0xb8,
    0xde, 0x8f, 0xe7, 0xc4, 0x45, 0xda, 0x86, 0xc4, 0x9b, 0x64, 0x8b, 0x14, 0x6a, 0xb4, 0xf1, 0xaa,
    0x38, 0x01, 0x35, 0x9e, 0x26, 0x69, 0x2c, 0x86, 0x00, 0x6b, 0x4f, 0xa5, 0x36, 0x34, 0x62, 0xa6,
    0x2a, 0x96, 0x68, 0x18, 0xf2, 0x4a, 0xfd, 0xbd, 0x6b, 0x97, 0x8f, 0x4d, 0x8f, 0x89, 0x13, 0xb7,
    0x6c, 0x8e, 0x93, 0xed, 0x0e, 0x0d, 0x48, 0x3e, 0xd7, 0x2f, 0x88, 0xd8, 0xfe, 0xfe, 0x7e, 0x86,
    0x50, 0x95, 0x4f, 0xd1, 0xeb, 0x83, 0x26, 0x34, 0xdb, 0x66, 0x7b, 0x9c, 0x7e, 0x9d, 0x7a, 0x81,
    0x32, 0xea, 0xb6, 0x33, 0xde, 0x3a, 0xa9, 0x59, 0x34, 0x66, 0x3b, 0xaa, 0xba, 0x81, 0x60, 0x48,
    0xb9, 0xd5, 0x81, 0x9c, 0xf8, 0x6c, 0x84, 0x77, 0xff, 0x54, 0x78, 0x26, 0x5f, 0xbe, 0xe8, 0x1e,
    0x36, 0x9f, 0x34, 0x80, 0x5c, 0x45, 0x2c, 0x9b, 0x76, 0xd5, 0x1b, 0x8f, 0xcc, 0xc3, 0xb8, 0xf5,
])
LONG_KEY = bytes([0x78, 0x06, 0xad, 0x4c, 0x33, 0x86, 0x5d, 0x18, 0x4c, 0x01, 0x3f, 0x46])


def new_key() -> bytes:
    return os.urandom(16)


def _derive_key(seed: bytes, size: int) -> bytes:
    out = bytearray(size)
    for i in range(size):
        out[i] = ((seed[i % len(seed)] + KEY_TABLE[size * i]) & 0xff) ^ KEY_TABLE[size * (size - 1 - i)]
    return bytes(out)


def _xor_transform(data: bytes, key: bytes) -> bytes:
    out = bytearray(data)
    offset = len(data) % 4
    for i in range(offset):
        out[i] ^= key[i % len(key)]
    for i in range(offset, len(out)):
        out[i] ^= key[(i - offset) % len(key)]
    return bytes(out)


def _symmetric_encode(data: bytes, key: bytes) -> bytes:
    b = _xor_transform(data, _derive_key(key, 4))
    b = b[::-1]
    return _xor_transform(b, LONG_KEY)


def _symmetric_decode(data: bytes, key: bytes, salt: bytes) -> bytes:
    b = _xor_transform(data, _derive_key(salt, 12))
    b = b[::-1]
    return _xor_transform(b, _derive_key(key, 4))


def _rsa_encrypt(data: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(data), RSA_PLAIN_CHUNK):
        chunk = data[i:i + RSA_PLAIN_CHUNK]
        block = bytearray(b"\xff" * RSA_BLOCK)
        block[0] = 0
        block[1] = 2
        sep = RSA_BLOCK - len(chunk) - 1
        block[sep] = 0
        block[sep + 1:RSA_BLOCK] = chunk
        m = int.from_bytes(bytes(block), "big")
        c = pow(m, EXPONENT, MODULUS)
        out += c.to_bytes(RSA_BLOCK, "big")
    return bytes(out)


def _rsa_decrypt(data: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(data), RSA_BLOCK):
        block = data[i:i + RSA_BLOCK]
        m = pow(int.from_bytes(block, "big"), EXPONENT, MODULUS)
        raw = m.to_bytes(RSA_BLOCK, "big")
        idx = raw.index(0, 2)
        out += raw[idx + 1:]
    return bytes(out)


def encode(payload: str) -> str:
    key = new_key()
    body = _symmetric_encode(payload.encode("utf-8"), key)
    plain = key + body
    return base64.b64encode(_rsa_encrypt(plain)).decode("ascii")


def decode(cipher_b64: str) -> str:
    raw = _rsa_decrypt(base64.b64decode(cipher_b64))
    salt, body = raw[:16], raw[16:]
    return _symmetric_decode(body, salt, salt).decode("utf-8")
