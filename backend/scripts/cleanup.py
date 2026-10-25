import asyncio
from app.db.session import engine
from app.workers.retention import cleanup_once


async def main():
    try:
        print(await cleanup_once())
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
