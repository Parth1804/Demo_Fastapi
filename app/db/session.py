# shareledger/app/db/session.py
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession
from app.core.config import settings

DATABASE_URL = settings.database_url
engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=False, future=True)


async def init_db():
    """
    Create tables (runs SQLModel.metadata.create_all in an async context).
    Called on app startup.
    """
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session():
    """
    Async session generator to use with Depends(get_db) or get_session wrapper.
    IMPORTANT: expire_on_commit=False prevents SQLAlchemy from expiring objects
    after commit which would otherwise cause lazy-loading (IO) during response
    serialization — leading to MissingGreenlet errors when called outside greenlet.
    """
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
