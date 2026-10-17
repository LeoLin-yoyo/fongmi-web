"""抖音 Web 风控签名 a_bogus（纯 Python 实现）。

算法参考 Evil0ctal/Douyin_TikTok_Download_API（Apache-2.0）与社区逆向资料，
按 Python 重写：SM3 哈希链 + RC4 + 自定义字母表 base64。

⚠️ 该算法跟随抖音前端 JS 变化。若接口返回空/验证码，说明算法已更新，
需要从最新 JS 重新校正 `_ARGUMENTS` / `_BROWSER` / `_REG` 等常量。
"""
import random
import time

from .sm3 import sm3_hash

# 自定义 base64 字母表（注意：非标准顺序）
_ALPHABET = "Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe="
# 参数标记
_ARGUMENTS = [0, 1, 14]
# UA 加密用的 RC4 密钥
_UA_KEY = "\u0000\u0001\u000e"
# 方法/参数哈希的后缀
_END_STRING = "cus"
# 浏览器指纹（窗口尺寸等，取自常见探测值）
_BROWSER = "1536|742|1536|864|0|0|0|0|1536|864|1536|864|1536|742|24|24|Win32"
# SM3 初始寄存器
_REG = [1937774191, 1226093241, 388252375, 3666478592,
        2842636476, 372324522, 3817729613, 2969243214]


def _sm3_to_array(data) -> list[int]:
    """SM3 摘要 → 32 个整数（每字节一个）。"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    h = sm3_hash(bytes(data))
    return [int(h[i:i + 2], 16) for i in range(0, len(h), 2)]


def _rc4_encrypt(plaintext: str, key: str) -> str:
    """标准 RC4，返回 latin1 字符串（与原实现逐码元对齐）。"""
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + ord(key[i % len(key)])) % 256
        s[i], s[j] = s[j], s[i]
    i = j = 0
    out = []
    for ch in plaintext:
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        out.append(chr(s[(s[i] + s[j]) % 256] ^ ord(ch)))
    return "".join(out)


def _char_code_at(text: str) -> list[int]:
    return [ord(c) for c in text]


def _random_list(r=None, a=170, b=85, d=0, e=0, f=0, g=0) -> list[int]:
    r = r if r is not None else random.random() * 10000
    v = [r, int(r) & 255, int(r) >> 8]
    v.append(v[1] & b | d)
    v.append(v[1] & a | e)
    v.append(v[2] & b | f)
    v.append(v[2] & a | g)
    return [int(x) & 255 for x in v[-4:]]


def _list_1(r=None):
    return _random_list(r, 170, 85, 1, 2, 5, 45 & 170)


def _list_2(r=None):
    return _random_list(r, 170, 85, 1, 0, 0, 0)


def _list_3(r=None):
    return _random_list(r, 170, 85, 1, 0, 5, 0)


def _generate_string_1(r1=None, r2=None, r3=None) -> str:
    return ("".join(chr(c) for c in _list_1(r1))
            + "".join(chr(c) for c in _list_2(r2))
            + "".join(chr(c) for c in _list_3(r3)))


def _generate_result(text: str) -> str:
    """自定义字母表 base64（补齐 = 号）。"""
    out = []
    for i in range(0, len(text), 3):
        chunk = text[i:i + 3]
        if len(chunk) == 3:
            n = (ord(chunk[0]) << 16) | (ord(chunk[1]) << 8) | ord(chunk[2])
        elif len(chunk) == 2:
            n = (ord(chunk[0]) << 16) | (ord(chunk[1]) << 8)
        else:
            n = ord(chunk[0]) << 16
        for shift, mask in zip((18, 12, 6, 0), (0xFC0000, 0x03F000, 0x0FC0, 0x3F)):
            if shift == 6 and len(chunk) < 2:
                break
            if shift == 0 and len(chunk) < 3:
                break
            out.append(_ALPHABET[(n & mask) >> shift])
    out.append("=" * ((4 - len(out) % 4) % 4))
    return "".join(out)


def _end_check_num(arr: list[int]) -> int:
    r = 0
    for x in arr:
        r ^= x & 0xFF
    return r


class ABogus:
    """为给定 User-Agent 生成 a_bogus。UA 必须与实际请求一致（签名绑定 UA）。"""

    def __init__(self, user_agent: str, browser_info: str = _BROWSER):
        self.user_agent = user_agent
        self.browser = browser_info
        self.browser_code = _char_code_at(self.browser)
        # UA 摘要链：RC4(UA) → base64 → SM3
        ua_rc4 = _rc4_encrypt(self.user_agent, _UA_KEY)
        self.ua_code = _sm3_to_array(_generate_result(ua_rc4))

    def _params_code(self, params: str) -> list[int]:
        return _sm3_to_array(_sm3_to_array(params + _END_STRING))

    def _method_code(self, method: str) -> list[int]:
        return _sm3_to_array(_sm3_to_array(method + _END_STRING))

    def _string2_list(self, params: str, method: str,
                      start_time: int, end_time: int) -> list[int]:
        p = self._params_code(params)
        m = self._method_code(method)
        ua = self.ua_code
        # 组装固定字段（顺序与原算法一致）
        return [
            44,
            (end_time >> 24) & 255, 0, 0, 0, 0, 24, p[21], 58, 0, ua[23], ua[24],
            0, 24, 97, 1, 0, 239, (end_time >> 16) & 255, 51, (end_time >> 8) & 255,
            end_time & 255, 0, 0, 0, 0, (start_time >> 24) & 255, 0, 0, 14,
            (start_time >> 16) & 255, (start_time >> 8) & 255, 0, start_time & 255,
            m[21], 3, 399, 1, 399, 1, 64, 0, 0, 0,
        ]

    def get_value(self, params: str, method: str = "GET",
                  start_time: int = 0, end_time: int = 0) -> str:
        """计算 a_bogus（未做 URL 编码）。params 为 query 串（不含 a_bogus）。"""
        start_time = start_time or int(time.time() * 1000)
        end_time = end_time or (start_time + random.randint(4, 8))
        arr = self._string2_list(params, method, start_time, end_time)
        check = _end_check_num(arr)
        arr.extend(self.browser_code)
        arr.append(check)
        s2 = _rc4_encrypt("".join(chr(c & 0xFF) for c in arr), "y")
        return _generate_result(_generate_string_1() + s2)


def sign_query(query: str, user_agent: str, method: str = "GET") -> str:
    """返回追加了 a_bogus 的 query 串。"""
    value = ABogus(user_agent).get_value(query, method)
    from urllib.parse import quote
    return f"{query}&a_bogus={quote(value, safe='')}"
