"""
SEPLE Tender Database — Async Connection Pool
Uses asyncpg for high-performance PostgreSQL access.
"""
import os
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Global connection pool
_pool = None


async def get_pool():
    """Get or create the async connection pool."""
    global _pool
    if _pool is None:
        import asyncpg
        database_url = os.getenv("DATABASE_URL", "postgresql://postgres:changeme@localhost:5432/tenders")
        _pool = await asyncpg.create_pool(
            database_url,
            min_size=2,
            max_size=10,
            command_timeout=60,
        )
        logger.info("Database connection pool created")
    return _pool


async def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")


@asynccontextmanager
async def get_connection():
    """Get a connection from the pool as an async context manager."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def health_check() -> bool:
    """Verify database connectivity."""
    try:
        async with get_connection() as conn:
            result = await conn.fetchval("SELECT 1")
            return result == 1
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


async def init_schema():
    """Initialize the database schema from schema.sql."""
    import pathlib
    schema_path = pathlib.Path(__file__).parent / "schema.sql"
    if not schema_path.exists():
        logger.error(f"Schema file not found: {schema_path}")
        return False

    schema_sql = schema_path.read_text()
    try:
        async with get_connection() as conn:
            await conn.execute(schema_sql)
        logger.info("Database schema initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Schema initialization failed: {e}")
        return False
