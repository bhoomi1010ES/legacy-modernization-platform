import asyncpg
import asyncio
import bcrypt

async def main():
    conn = await asyncpg.connect("postgresql://postgres:postres123@127.0.0.1:5432/rebase")
    user = await conn.fetchrow("SELECT password_hash FROM users WHERE email = 'bhoomi.edgesphere@gmail.com'")
    ph = user["password_hash"]
    test_passwords = ["Parth@0911", "admin123", "password", "bhoomi123", "Bhoomi@123", "EdgeSphere@2026", "secret123"]
    for p in test_passwords:
        res = bcrypt.checkpw(p.encode("utf-8"), ph.encode("utf-8"))
        print(f"Password '{p}': {res}")
    
    # Also update Bhoomi's password to 'Parth@0911' so user can log in with the password they are typing in the UI!
    new_hash = bcrypt.hashpw("Parth@0911".encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")
    await conn.execute("UPDATE users SET password_hash = $1 WHERE email = 'bhoomi.edgesphere@gmail.com'", new_hash)
    print("Updated password to Parth@0911!")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())

