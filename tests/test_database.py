"""
Test: Is PostgreSQL running and schema created?
Run: python tests/test_database.py
"""
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()


async def test_db():
    import asyncpg

    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:changeme@localhost:5432/tenders")
    # never print credentials — mask everything between '://' and '@'
    print(f"Connecting to: postgresql://***@{db_url.rsplit('@', 1)[-1]}")

    try:
        conn = await asyncpg.connect(db_url)
        print("Connection successful")

        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)

        print("\n--- TABLES IN DATABASE ---")
        for t in tables:
            print(f"  {t['table_name']}")

        await conn.close()
        print("\nDatabase test passed")

    except Exception as e:
        print(f"Database connection failed: {e}")
        print("Make sure Docker is running: docker-compose up db -d")


if __name__ == "__main__":
    asyncio.run(test_db())
