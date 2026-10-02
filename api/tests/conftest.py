"""API 测试共享夹具"""
import tempfile
import os
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# 使用临时目录数据库（mkdtemp 原子创建，避免 mktemp 的竞态问题）
_TEST_DB_DIR = tempfile.mkdtemp(prefix="fongmi_test_db_")
TEST_DB_FILE = os.path.join(_TEST_DB_DIR, "test.db")
TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_FILE}"

# 导入 model.database 后，用 configure() 修改现有 session 的绑定，而不是替换变量
import model.database as db_mod

# 创建新引擎
new_engine = create_async_engine(TEST_DB_URL, echo=False)
# 用 configure 修改 async_session 的绑定，这样所有引用同一对象的地方都会生效
db_mod.async_session.configure(bind=new_engine)
# 更新 engine 引用
db_mod.engine = new_engine

from model.database import engine, async_session, Base
from api import api_router


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """session 级别：建表一次，测试完清理"""
    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(_create())
    yield
    async def _drop():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    asyncio.run(_drop())


@pytest.fixture(autouse=True)
def clean_data():
    """每个测试前清空数据"""
    async def _clean():
        async with async_session() as session:
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(table.delete())
            await session.commit()
    asyncio.run(_clean())
    yield


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(api_router, prefix="/api")
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def cleanup():
    try:
        os.unlink(TEST_DB_FILE)
    except OSError:
        pass


import atexit
atexit.register(cleanup)