import asyncpg
import asyncio

async def main():
    conn = await asyncpg.connect("postgresql://postgres:postres123@127.0.0.1:5432/rebase")
    job = await conn.fetchrow("SELECT * FROM jobs WHERE job_id = '26b905d7-0013-4dd2-84ec-39d8809d280b'")
    for k, v in dict(job).items():
        print(f"{k}: {v}")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())

