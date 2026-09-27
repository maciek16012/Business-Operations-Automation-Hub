import os
import uuid

import httpx
import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_service
from app.db.base import Base
from app.extraction.development import DevelopmentExtractionProvider
from app.main import app
from app.services.cases import CaseService
from app.storage.base import LocalFilesystemStorage


@pytest.fixture
async def client(tmp_path):
    url = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite://")
    schema = "test_" + uuid.uuid4().hex
    admin = None
    if url.startswith("postgresql"):
        admin = create_async_engine(url)
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    else:
        engine = create_async_engine(url)

        @event.listens_for(engine.sync_engine, "connect")
        def foreign_keys(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    storage = LocalFilesystemStorage(str(tmp_path / "objects"))

    async def override():
        async with sessions() as session:
            yield CaseService(session, storage, DevelopmentExtractionProvider())

    app.dependency_overrides[get_service] = override
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http
    app.dependency_overrides.clear()
    await engine.dispose()
    if admin:
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()
