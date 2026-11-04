import asyncpg
import asyncio
import json

async def inspect():
    conn = await asyncpg.connect('postgresql://postgres:postres123@localhost:5432/rebase')
    tables = ['jobs', 'modules', 'module_attempts', 'workflow_gates', 'gate_decisions', 
              'workflow_checkpoints', 'workflow_outbox', 'artifacts', 'tasks']
    for t in tables:
        cols = await conn.fetch(f"""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = '{t}' 
            ORDER BY ordinal_position
        """)
        print(f"=== {t} columns ===")
        print([f"{c['column_name']} ({c['data_type']})" for c in cols])
    await conn.close()

if __name__ == '__main__':
    asyncio.run(inspect())

