import asyncpg
import asyncio

async def main():
    conn = await asyncpg.connect("postgresql://postgres:postres123@127.0.0.1:5432/rebase")
    cols = await conn.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'users'")
    for c in cols:
        print(c["column_name"], c["data_type"])
    users = await conn.fetch("SELECT * FROM users")
    for u in users:
        print(dict(u))
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
