import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.db import Base
from app import models  # noqa: F401  -- import registers tables on Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


# Arbitrary but fixed: every migration runner in this system must agree on it.
_ADVISORY_LOCK_KEY = 7281490011


def _do_run(connection: Connection) -> None:
    """Run migrations under a Postgres advisory lock.

    Every backend pod runs `alembic upgrade head` in an init container, so on a
    rollout several replicas can attempt to migrate at the same moment. The
    lock serialises them: the first acquires it and applies the migration, the
    rest block and then find the schema already at head and do nothing.

    A *session*-level lock is the right primitive: Postgres releases it when the
    connection dies, so an OOM-killed migration pod cannot wedge the next
    rollout. It also survives the commits below, which a transaction-scoped
    lock (`pg_advisory_xact_lock`) would not.

    The explicit commits are load-bearing. Acquiring the lock issues a
    statement, which opens an implicit transaction; leaving it open would nest
    Alembic's own transaction inside it, and the DDL would be silently rolled
    back when the connection closed -- migrations that log success and change
    nothing.
    """
    is_postgres = connection.dialect.name == "postgresql"

    if is_postgres:
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _ADVISORY_LOCK_KEY})
        connection.commit()

    try:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        connection.commit()
    finally:
        if is_postgres:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _ADVISORY_LOCK_KEY})
            connection.commit()


async def run_migrations_online() -> None:
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(_do_run)
    await engine.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
