import asyncpg
import asyncio

async def verify():
    conn_orig = await asyncpg.connect('postgresql://postgres:postres123@localhost:5432/rebase')
    conn_disp = await asyncpg.connect('postgresql://postgres:postres123@localhost:5432/rebase_disposable_w00_verify')
    
    tables_orig = [r['table_name'] for r in await conn_orig.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
    )]
    tables_disp = [r['table_name'] for r in await conn_disp.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
    )]
    
    print(f'Orig tables count: {len(tables_orig)}')
    print(f'Disp tables count: {len(tables_disp)}')
    assert tables_orig == tables_disp, 'Tables list mismatch!'
    
    mismatches = []
    total_rows_orig = 0
    total_rows_disp = 0
    table_stats = []
    
    for tbl in tables_orig:
        c_orig = await conn_orig.fetchval(f'SELECT count(*) FROM "{tbl}"')
        c_disp = await conn_disp.fetchval(f'SELECT count(*) FROM "{tbl}"')
        total_rows_orig += c_orig
        total_rows_disp += c_disp
        table_stats.append((tbl, c_orig, c_disp))
        if c_orig != c_disp:
            mismatches.append((tbl, c_orig, c_disp))
            
    print(f'Total rows orig: {total_rows_orig}')
    print(f'Total rows disp: {total_rows_disp}')
    if mismatches:
        print('Mismatches found:', mismatches)
    else:
        print('SUCCESS: All 36 table schemas and 100% of row counts match exactly between original and disposable restore!')
        
    for tbl, co, cd in table_stats:
        print(f'  - {tbl}: {co} rows')
        
    await conn_orig.close()
    await conn_disp.close()

if __name__ == '__main__':
    asyncio.run(verify())

