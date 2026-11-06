import asyncpg
import asyncio

async def main():
    conn = await asyncpg.connect("postgresql://postgres:postres123@127.0.0.1:5432/rebase")
    await conn.execute("UPDATE jobs SET max_repair_attempts = 20 WHERE job_id = '26b905d7-0013-4dd2-84ec-39d8809d280b'")
    await conn.close()
    print("Updated max_repair_attempts to 20!")

if __name__ == "__main__":
    asyncio.run(main())
