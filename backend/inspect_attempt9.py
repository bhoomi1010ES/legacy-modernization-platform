import asyncpg
import asyncio
import json
import uuid

async def main():
    conn = await asyncpg.connect("postgresql://postgres:postres123@127.0.0.1:5432/rebase")
    attempt_id = uuid.UUID("c9a2e59e-cded-4daa-bf27-d6804ea8ff90")
    vr = await conn.fetchrow(
        "SELECT evidence, status FROM verification_runs WHERE attempt_id = $1",
        attempt_id
    )
    if vr:
        print("VERIFICATION RUN STATUS:", vr["status"])
        ev = json.loads(vr["evidence"])
        v = ev.get("verification", {})
        print("Verification passed?:", v.get("passed"))
        print("\nCHECKS:")
        for c in v.get("checks", []):
            print(f"  [{c.get('status')}] Category: {c.get('category')}, exit: {c.get('exit_code')}")
        print("\nCASES SUMMARY:")
        cases = v.get("cases", [])
        passed_cases = sum(1 for c in cases if c.get("status") == "PASS")
        print(f"Total Cases: {len(cases)}, Passed Cases: {passed_cases}")
        if passed_cases < len(cases):
            print("Failed cases sample:")
            for c in cases:
                if c.get("status") != "PASS":
                    print(f"  Case {c.get('test_case_id')}: status={c.get('status')}, exit={c.get('exit_code')}, stderr={c.get('stderr')[:100] if c.get('stderr') else ''}")
        print("\nREVIEW:")
        rev = ev.get("review", {})
        print("Review status:", rev.get("status"), "findings count:", len(rev.get("findings", [])))
        for f in rev.get("findings", []):
            print("  Finding:", f)
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())

