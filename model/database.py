from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, DateTime, UniqueConstraint, ForeignKey, func, select, update
from datetime import datetime
import os

DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "fongmi.db")
os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Config(Base):
    __tablename__ = "config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    url: Mapped[str] = mapped_column(String(1024), default="")
    type: Mapped[str] = mapped_column(String(16), default="vod")
    content: Mapped[str] = mapped_column(Text, default="")
    hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("hash", name="uq_config_hash"),)


class Site(Base):
    __tablename__ = "site"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_id: Mapped[int] = mapped_column(Integer, ForeignKey("config.id"), index=True)
    key: Mapped[str] = mapped_column(String(128), default="")
    name: Mapped[str] = mapped_column(String(255), default="")
    type: Mapped[int] = mapped_column(Integer, default=0)
    api: Mapped[str] = mapped_column(String(1024), default="")
    ext: Mapped[str] = mapped_column(Text, default="")
    player_type: Mapped[int] = mapped_column(Integer, default=0)
    searchable: Mapped[int] = mapped_column(Integer, default=1)
    quick_search: Mapped[int] = mapped_column(Integer, default=1)
    filterable: Mapped[int] = mapped_column(Integer, default=1)


class Parse(Base):
    __tablename__ = "parse"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_id: Mapped[int] = mapped_column(Integer, ForeignKey("config.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    url: Mapped[str] = mapped_column(String(1024), default="")
    type: Mapped[int] = mapped_column(Integer, default=0)
    ext: Mapped[str] = mapped_column(Text, default="")


class History(Base):
    __tablename__ = "history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_key: Mapped[str] = mapped_column(String(128), default="")
    vod_id: Mapped[str] = mapped_column(String(255), default="")
    name: Mapped[str] = mapped_column(String(512), default="")
    pic: Mapped[str] = mapped_column(String(1024), default="")
    episode: Mapped[str] = mapped_column(String(255), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    duration: Mapped[int] = mapped_column(Integer, default=0)
    time: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class LiveSource(Base):
    __tablename__ = "live_source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    url: Mapped[str] = mapped_column(String(1024), default="")
    type: Mapped[str] = mapped_column(String(16), default="m3u")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    group_count: Mapped[int] = mapped_column(Integer, default=0)
    channel_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class Keep(Base):
    __tablename__ = "keep"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_key: Mapped[str] = mapped_column(String(128), default="")
    vod_id: Mapped[str] = mapped_column(String(255), default="")
    name: Mapped[str] = mapped_column(String(512), default="")
    pic: Mapped[str] = mapped_column(String(1024), default="")
    type: Mapped[str] = mapped_column(String(16), default="vod")
    time: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class DownloadTask(Base):
    """统一下载任务：TG / 网盘 / 直链共用一套分片断点引擎。"""

    __tablename__ = "download_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(16), default="url")  # tg / pan / url
    name: Mapped[str] = mapped_column(String(512), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    headers: Mapped[str] = mapped_column(Text, default="")          # JSON：请求头（含 Cookie）
    folder: Mapped[str] = mapped_column(String(1024), default="")
    filename: Mapped[str] = mapped_column(String(512), default="")
    file_path: Mapped[str] = mapped_column(String(1024), default="")
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[int] = mapped_column(Integer, default=0)
    speed: Mapped[int] = mapped_column(Integer, default=0)          # 字节/秒 EMA
    block: Mapped[int] = mapped_column(Integer, default=0)          # 0=用引擎默认 8MiB
    connections: Mapped[int] = mapped_column(Integer, default=0)    # 0=用引擎默认
    extra: Mapped[str] = mapped_column(Text, default="")            # JSON：来源上下文（fid/口令等）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class PanAccount(Base):
    """网盘账号：Cookie 凭证 AES-GCM 加密落库（每平台一条）。"""

    __tablename__ = "pan_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    cookie: Mapped[str] = mapped_column(Text, default="")           # 密文
    nickname: Mapped[str] = mapped_column(String(255), default="")
    valid: Mapped[int] = mapped_column(Integer, default=1)          # 最近一次登录态校验结果
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        result = await session.execute(
            select(Config).where(Config.enabled == 1).limit(1)
        )
        if result.scalar_one_or_none() is None:
            await session.execute(
                update(Config).where(Config.id > 0).values(enabled=1, priority=Config.id)
            )
            await session.commit()

        # 回填历史遗留的占位名：早期导入把无 name 字段的配置统一存成 "Imported Config"
        stale = await session.execute(
            select(Config).where(Config.name.in_(["Imported Config", ""]))
        )
        stale_configs = stale.scalars().all()
        if stale_configs:
            from api.config import derive_config_name
            for cfg in stale_configs:
                try:
                    import json as _json
                    data = _json.loads(cfg.content) if cfg.content else {}
                    if not isinstance(data, dict):
                        data = {}
                except Exception:
                    data = {}
                cfg.name = derive_config_name(data, cfg.url or "")
            await session.commit()


async def get_db():
    async with async_session() as session:
        yield session
