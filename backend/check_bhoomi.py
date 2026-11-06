import asyncpg
import asyncio

async def main():
    conn = await asyncpg.connect("postgresql://postgres:postres123@127.0.0.1:5432/rebase")
    user = await conn.fetchrow("SELECT * FROM users WHERE email = 'bhoomi.edgesphere@gmail.com'")
    print("Bhoomi user:", dict(user) if user else "NOT FOUND")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())

