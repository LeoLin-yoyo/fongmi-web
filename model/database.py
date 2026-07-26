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


async def get_db():
    async with async_session() as session:
        yield session
