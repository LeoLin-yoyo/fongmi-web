"""网盘通用数据模型与异常。"""
from dataclasses import dataclass, field


class PanError(Exception):
    """网盘接口错误；code 为平台错误码（如有）"""

    def __init__(self, message: str, code: int = 0):
        super().__init__(message)
        self.code = code


@dataclass
class ShareSession:
    """一次分享链接解析出的会话（对齐 YunX ShareSession）"""
    platform: str = ""
    share_id: str = ""        # 分享短码（pwd_id）
    passcode: str = ""        # 提取码
    stoken: str = ""          # 分享访问凭证
    title: str = ""
    first_fid: str = "0"      # 根条目 fid
    raw: dict = field(default_factory=dict)


@dataclass
class ShareFile:
    """分享内的文件/目录条目（对齐 YunX ShareFile）"""
    fid: str = ""
    fname: str = ""
    fsize: int = 0
    isdir: bool = False
    pdir_fid: str = ""
    fid_token: str = ""       # 分享侧 fid_token（share_fid_token），取链要用
    updated_at: str = ""
    children: list = field(default_factory=list)  # 目录树（浏览时不预填）

    def to_dict(self) -> dict:
        return {
            "fid": self.fid, "fname": self.fname, "fsize": self.fsize,
            "isdir": self.isdir, "pdir_fid": self.pdir_fid,
            "fid_token": self.fid_token, "updated_at": self.updated_at,
        }


@dataclass
class DownloadLink:
    """下载/播放直链（对齐 YunX DownloadLink）"""
    fid: str = ""
    filename: str = ""
    url: str = ""
    size: int = 0
    headers: dict = field(default_factory=dict)   # 必须随请求发送的头（Cookie 参与签名）
    guest_cookie: str = ""                        # 游客态 CDN Cookie（__pugs）
    play_url: str = ""                            # 平台转码播放地址（UC file/v2/play，可选）
    # 服务端签发元信息
    token: str = ""
    platform: str = ""
    share_id: str = ""
