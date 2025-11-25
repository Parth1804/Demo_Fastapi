from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession
from app.core.config import settings
from sqlalchemy import create_engine as create_sync_engine


DATABASE_URL = settings.database_url
engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=False, future=True)


sync_engine = create_sync_engine(
    settings.database_url.replace("+asyncpg", ""),  # convert async → sync URL
    future=True,
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session():
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
