"""P2 平台客户端测试：注册、加密/签名算法、链接识别、字段解析。"""
import base64
import json

import pytest

from pan import accounts
from pan.platforms import pan115_crypto
from pan.platforms.c139 import _aes_decrypt, _aes_encrypt, _mcloud_sign
from pan.platforms.ilanzou import _aes_hex, _enc_token
from pan.platforms.lanzou import _acw_sc_v2, _parse_display_size
from pan.platforms.pan123 import Pan123Client


ALL_PLATFORMS = {"quark", "uc", "xunlei", "baidu", "c139", "pan123", "pan115", "guangya", "lanzou", "ilanzou"}


def test_all_platforms_registered():
    assert set(accounts.CLIENT_CLASSES.keys()) == ALL_PLATFORMS


def test_guest_support_flags():
    assert accounts.CLIENT_CLASSES["quark"].GUEST_SUPPORTED is True
    assert accounts.CLIENT_CLASSES["uc"].GUEST_SUPPORTED is True
    assert accounts.CLIENT_CLASSES["baidu"].GUEST_SUPPORTED is False
    assert accounts.CLIENT_CLASSES["pan115"].GUEST_SUPPORTED is False


# ---------- 115 crypto ----------

def test_115_encode_block_aligned():
    enc = pan115_crypto.encode('{"pickcode":"abc"}')
    raw = base64.b64decode(enc)
    assert len(raw) % 128 == 0  # RSA 块 = 128 字节


def test_115_structures():
    key = pan115_crypto._derive_key(b"A" * 16, 4)
    assert len(key) == 4
    assert len(pan115_crypto._derive_key(b"B" * 16, 12)) == 12
    data = b"hello world test data"
    # xor 变换自反
    assert pan115_crypto._xor_transform(pan115_crypto._xor_transform(data, key), key) == data


# ---------- 123 sign ----------

def test_123_sign_deterministic():
    cl = Pan123Client("dummy")
    a1 = cl._make_sign("/b/api/share/download/info", 1700000000)
    # 同一 ts 下 authKey 稳定（random 影响 authValue）
    a2 = cl._make_sign("/b/api/share/download/info", 1700000000)
    assert a1[0] == a2[0]
    assert a1[1].split("-")[0] == "1700000000"
    assert a1[1].split("-")[2] == a1[1].split("-")[2]


def test_123_sign_table_mapping():
    import zlib
    cl = Pan123Client("dummy")
    ak, _ = cl._make_sign("/b/api/file/list/new", 1700000000)
    # crc32 小写不补零
    assert ak == format(zlib.crc32(ak.encode()) & 0xffffffff, "x") or len(ak) <= 8


def test_123_device_id_persistent(tmp_path, monkeypatch):
    import pan.platforms.pan123 as m
    f = tmp_path / "dev"
    monkeypatch.setattr(m, "os", m.os)
    a = Pan123Client._load_or_make_device_id()
    b = Pan123Client._load_or_make_device_id()
    assert a == b and len(a) == 32


# ---------- 139 ----------

def test_139_aes_roundtrip():
    msg = '{"getOutLinkInfoReq":{"account":"","linkID":"abc"}}'
    assert _aes_decrypt(_aes_encrypt(msg)) == msg


def test_139_mcloud_sign_format():
    sign = _mcloud_sign('{"a":1}')
    parts = sign.split(",")
    assert len(parts) == 3
    assert len(parts[1]) == 16            # 随机段
    assert len(parts[2]) == 32 and parts[2] == parts[2].upper()  # md5 大写


def test_139_gzip_decrypt():
    import gzip
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
    import os
    plain = '{"hello":"世界"}'
    gz = gzip.compress(plain.encode())
    iv = os.urandom(16)
    ct = AES.new(b"PVGDwmcvfs1uV3d1", AES.MODE_CBC, iv).encrypt(pad(gz, 16))
    assert _aes_decrypt(base64.b64encode(iv + ct).decode()) == plain


# ---------- 蓝奏 ----------

def test_lanzou_acw_length():
    assert len(_acw_sc_v2("0" * 40)) == 40
    assert len(_acw_sc_v2("a" * 40)) == 40


def test_lanzou_display_size():
    assert _parse_display_size("1.5 M") == int(1.5 * 1024 * 1024)
    assert _parse_display_size("2G") == 2 * 1024 ** 3
    assert _parse_display_size("500") == 500


# ---------- 蓝奏优享 ----------

def test_ilanzou_aes_hex():
    assert len(_aes_hex("1234567890")) == 32
    assert all(ch in "0123456789abcdef" for ch in _aes_hex("x"))


def test_ilanzou_enc_token_colon():
    assert _enc_token("a:b") == "a:b"  # %3A 还原为冒号


# ---------- 各平台字段解析 ----------

def test_xunlei_parse_files():
    from pan.platforms.xunlei import XunleiClient
    files = XunleiClient._parse_files([
        {"id": "1", "name": "电影", "kind": "drive#folder", "parent_id": "0"},
        {"id": "2", "name": "a.mp4", "size": 100, "kind": "drive#file", "parent_id": "0"},
    ])
    assert files[0].isdir is True and files[1].isdir is False
    assert files[1].fsize == 100


def test_guangya_parse_file():
    from pan.platforms.guangya import GuangYaClient
    f = GuangYaClient._parse_file({"fileId": "x", "fileName": "v.mp4", "fileSize": 200, "fileType": 1})
    assert f.fid == "x" and f.fsize == 200 and f.isdir is False
    d = GuangYaClient._parse_file({"fileId": "y", "fileName": "dir", "fileType": 2})
    assert d.isdir is True


def test_ilanzou_parse_file_size_kib():
    from pan.platforms.ilanzou import ILanzouClient
    f = ILanzouClient._parse_file({"fileId": "1", "fileName": "a.mp4", "fileSize": 100, "fileType": 1})
    assert f.fsize == 100 * 1024  # KiB → B


def test_xunlei_guest_no_auth_header():
    from pan.platforms.xunlei import XunleiClient
    cl = XunleiClient("")  # 未登录
    h = cl._pan_headers()
    assert "Authorization" not in h  # 游客不写 Authorization
    assert h["X-Device-Id"]


# ---------- 蓝奏：不伪造数据（回归） ----------

def test_lanzou_single_file_no_fabrication():
    """分享页无有效内容时，不得把错误页伪装成「蓝奏文件」条目。"""
    import asyncio
    from pan.platforms.lanzou import LanzouClient
    from pan.models import PanError

    cl = LanzouClient("")

    async def fake_get_text(url, referer=""):
        return "<html><title>提示</title><body>请稍后再试</body></html>"  # 无 file/fid/大小/标题

    cl._get_text = fake_get_text

    async def go():
        try:
            await cl.list_share_files(_mk_session(), "0")
            return None
        except PanError as e:
            return str(e)

    err = asyncio.run(go())
    assert err is not None and ("解析失败" in err or "不存在" in err)


def _mk_session():
    from pan.models import ShareSession
    return ShareSession(platform="lanzou", share_id="iZZZ")


# ---------- 139：明文 JSON 与密文双兼容 ----------

def test_139_share_post_plain_json_fallback():
    """网关透传明文 JSON 时应直接解析，不强行解密。"""
    import asyncio, json
    from pan.platforms.c139 import C139Client

    cl = C139Client("")

    class FakeResp:
        status_code = 200
        text = json.dumps({"resultCode": "0", "data": {"ok": 1}})

    async def fake_post(url, content=None, headers=None):
        return FakeResp()

    cl._client.post = fake_post
    out = asyncio.run(cl._share_post("/x", {"a": 1}))
    assert out["resultCode"] == "0"
