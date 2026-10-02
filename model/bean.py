from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Union
from datetime import datetime
import json


class Site(BaseModel):
    key: str = ""
    name: str = ""
    type: int = 0
    api: str = ""
    playUrl: str = ""
    searchable: int = 1
    quickSearch: int = 1
    filterable: int = 1
    ext: Union[str, dict, list] = ""
    jar: str = ""
    playerType: int = 0
    categories: list = []
    header: dict = {}
    style: dict = {}
    playerUrl: str = ""
    clickSelector: str = ""

    def get_ext_str(self) -> str:
        if isinstance(self.ext, (dict, list)):
            return json.dumps(self.ext, ensure_ascii=False)
        return self.ext


class Parse(BaseModel):
    name: str
    url: str
    type: int = 0
    ext: dict = {}
    header: dict = {}


class Live(BaseModel):
    name: str = ""
    type: int = 0
    url: str = ""
    epg: str = ""
    logo: str = ""
    boot: bool = False
    channels: list = []
    pass_: bool = Field(False, alias="pass")

    model_config = ConfigDict(populate_by_name=True)


class Proxy(BaseModel):
    doh: str = ""
    url: str = ""
    ips: list = []


class VodConfig(BaseModel):
    sites: list[Site] = []
    parses: list[Parse] = []
    lives: list[Live] = []
    doh: list = []
    rules: list = []
    flags: list[str] = []
    ads: list[str] = []
    wall: str = ""
    spider: str = ""


class History(BaseModel):
    id: int
    site_key: str = ""
    vod_id: str = ""
    name: str = ""
    pic: str = ""
    episode: str = ""
    position: int = 0
    duration: int = 0
    time: datetime

    model_config = ConfigDict(from_attributes=True)


class Keep(BaseModel):
    id: int
    site_key: str = ""
    vod_id: str = ""
    name: str = ""
    pic: str = ""
    type: str = "vod"
    time: datetime

    model_config = ConfigDict(from_attributes=True)


class HistoryCreate(BaseModel):
    site_key: str = ""
    vod_id: str = ""
    name: str = ""
    pic: str = ""
    episode: str = ""
    position: int = 0
    duration: int = 0


class KeepCreate(BaseModel):
    site_key: str = ""
    vod_id: str = ""
    name: str = ""
    pic: str = ""
    type: str = "vod"


class ConfigImportRequest(BaseModel):
    url: Optional[str] = None
    json_: Optional[dict] = Field(None, alias="json")

    model_config = ConfigDict(populate_by_name=True)
