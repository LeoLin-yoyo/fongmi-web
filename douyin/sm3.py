"""SM3 国密哈希（a_bogus 签名依赖）。

纯 Python 实现，参照 GB/T 32905-2016。仅暴露 `sm3_hash(data) -> hex str`。
"""
import struct

IV = [
    0x7380166F, 0x4914B2B9, 0x172442D7, 0xDA8A0600,
    0xA96F30BC, 0x163138AA, 0xE38DEE4D, 0xB0FB0E4E,
]
T_J = [0x79CC4519, 0x7A879D8A]


def _rotl(x: int, n: int) -> int:
    n &= 31
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _ff(j: int, x: int, y: int, z: int) -> int:
    return (x ^ y ^ z) if j < 16 else ((x & y) | (x & z) | (y & z))


def _gg(j: int, x: int, y: int, z: int) -> int:
    return (x ^ y ^ z) if j < 16 else ((x & y) | (~x & z) & 0xFFFFFFFF)


def _p0(x: int) -> int:
    return x ^ _rotl(x, 9) ^ _rotl(x, 17)


def _p1(x: int) -> int:
    return x ^ _rotl(x, 15) ^ _rotl(x, 23)


def _compress(v: list[int], block: bytes) -> None:
    w = list(struct.unpack(">16I", block))
    for j in range(16, 68):
        w.append(_p1(w[j - 16] ^ w[j - 9] ^ _rotl(w[j - 3], 15))
                 ^ _rotl(w[j - 13], 7) ^ w[j - 6])
    w1 = [w[j] ^ w[j + 4] for j in range(64)]

    a, b, c, d, e, f, g, h = v
    for j in range(64):
        if j < 16:
            a12 = _rotl(a, 12)
            ss1 = _rotl((a12 + e + _rotl(T_J[0], j)) & 0xFFFFFFFF, 7)
            ss2 = ss1 ^ a12
            tt1 = (_ff(j, a, b, c) + d + ss2 + w1[j]) & 0xFFFFFFFF
            tt2 = (_gg(j, e, f, g) + h + ss1 + w[j]) & 0xFFFFFFFF
        else:
            a12 = _rotl(a, 12)
            ss1 = _rotl((a12 + e + _rotl(T_J[1], j % 32)) & 0xFFFFFFFF, 7)
            ss2 = ss1 ^ a12
            tt1 = (_ff(j, a, b, c) + d + ss2 + w1[j]) & 0xFFFFFFFF
            tt2 = (_gg(j, e, f, g) + h + ss1 + w[j]) & 0xFFFFFFFF
        d = c
        c = _rotl(b, 9)
        b = a
        a = tt1
        h = g
        g = _rotl(f, 19)
        f = e
        e = _p0(tt2)
    for i, x in enumerate((a, b, c, d, e, f, g, h)):
        v[i] ^= x


def sm3_hash(data: bytes) -> str:
    """返回 64 位十六进制摘要。"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    v = IV[:]
    bit_len = len(data) * 8
    padded = data + b"\x80"
    while len(padded) % 64 != 56:
        padded += b"\x00"
    padded += struct.pack(">Q", bit_len)
    for i in range(0, len(padded), 64):
        _compress(v, padded[i:i + 64])
    return "".join(f"{x:08x}" for x in v)
