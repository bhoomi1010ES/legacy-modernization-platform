import asyncpg
import asyncio
import json

async def main():
    conn = await asyncpg.connect("postgresql://postgres:postres123@127.0.0.1:5432/rebase")
    attempt_id = "338e8c91-7e2a-4033-9e28-5340b8ffa698"
    
    vr = await conn.fetchrow("SELECT * FROM verification_runs WHERE attempt_id = $1", attempt_id)
    if vr:
        print("VERIFICATION RUN STATUS:", vr["status"])
        ev = json.loads(vr["evidence"]) if isinstance(vr["evidence"], str) else vr["evidence"]
        v = ev.get("verification", {})
        print("Verification passed?:", v.get("passed"))
        print("CHECKS:")
        for c in v.get("checks", []):
            print(f"  Category: {c.get('category')}, status: {c.get('status')}, exit: {c.get('exit_code')}, tool: {c.get('tool_name')}")
            if c.get("stderr"):
                print(f"    stderr: {c.get('stderr')[:300]}")
        print("REVIEW:")
        rev = ev.get("review", {})
        print("Review status:", rev.get("status"), "findings count:", len(rev.get("findings", [])))
        for f in rev.get("findings", []):
            print("  Finding:", f)
            
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())

