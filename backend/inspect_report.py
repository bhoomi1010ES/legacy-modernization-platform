import asyncio
import json
from app.core.database import AsyncSessionLocal
from app.services import phase5_service as service

async def main():
    async with AsyncSessionLocal() as db:
        rep = await service.report(db, '461eaa69-70b5-4396-8fab-c057f8594d3b')
        print("KEYS:", list(rep.keys()))
        print("SCHEMA_STATUS:", rep.get("schema_status"))
        print("SCHEMA_VAL_STATUS:", rep.get("schema_validation_status"))
        print("SUITE_ID:", rep.get("suite_id"))
        print("CONTENT_HASH:", rep.get("content_hash"))
        print("STATUS:", rep.get("status"))
        print("GATE_ID:", rep.get("gate_id"))
        cases = rep.get("cases", [])
        print("CASES COUNT:", len(cases))
        outcomes = {}
        for c in cases:
            o = c.get("outcome")
            outcomes[o] = outcomes.get(o, 0) + 1
        print("OUTCOMES:", outcomes)
        print("G2 READINESS:", rep.get("g2_readiness"))

if __name__ == '__main__':
    asyncio.run(main())

