import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ENVIRONMENT"] = "test"


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.config import get_settings
    from app.db import Base, session as session_mod
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # The app lifespan is not run by ASGITransport, so build the engine here
        # and create the schema directly (Alembic covers the real databases).
        async with session_mod.lifespan_engine() as engine:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            yield ac


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"
