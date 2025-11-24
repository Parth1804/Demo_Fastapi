import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def test():
    print("Using DB URL:", settings.database_url)

    try:
        engine = create_async_engine(
            settings.database_url,
            echo=False,
            future=True
        )
    except Exception as e:
        print("ENGINE CREATION FAILED:", type(e).__name__, e)
        return

    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: None)
        print("DB OK")
    except Exception as e:
        print("DB ERROR:", type(e).__name__, e)

if __name__ == "__main__":
    asyncio.run(test())
