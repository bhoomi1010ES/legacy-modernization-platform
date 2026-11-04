"""Back up, apply tested forward migrations, and verify preserved live history."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))


async def main(args):
    import asyncpg
    from sqlalchemy.engine import make_url
    from app.core.config import settings
    if args.output.exists():raise ValueError('Migration evidence must not be overwritten')
    accepted=json.loads((ROOT/'docs/audits/W09_MIGRATIONS_20261102.json').read_text())
    if accepted['status']!='PASS' or accepted['to_revision']!='f1b2c3d4e5f6':raise ValueError('Matching isolated PostgreSQL migration acceptance is required')
    url=make_url(settings.DATABASE_URL)
    if url.host not in {'localhost','127.0.0.1'}:raise ValueError('Expected verified local PostgreSQL connection')
    db=await asyncpg.connect(url.set(drivername='postgresql').render_as_string(hide_password=False))
    before=await db.fetchval('SELECT version_num FROM alembic_version')
    if before not in {'d9e0f1a2b3c4','e9f0a1b2c3d4','f0a1b2c3d4e5','f1b2c3d4e5f6'}:raise ValueError('Unexpected live database revision; migration not applied')
    old_artifacts={str(r['artifact_id']):r['content_hash'] for r in await db.fetch('SELECT artifact_id,content_hash FROM artifacts')}
    counts={name:await db.fetchval('SELECT count(*) FROM '+name) for name in ('jobs','artifacts','gate_decisions','workflow_gates','module_attempts','verification_runs','model_gateway_requests')}
    backup=ROOT/'backups'/('w09-before-forward-migrations-'+str(time.time_ns())+'.dump');backup.parent.mkdir(exist_ok=True)
    if backup.exists():raise ValueError('Backup collision')
    executable=shutil.which('pg_dump') or str(Path(os.environ.get('ProgramFiles','C:/Program Files'))/'PostgreSQL/18/bin/pg_dump.exe')
    environment=os.environ.copy();environment.update(PGHOST=url.host,PGPORT=str(url.port or 5432),PGUSER=url.username or '',PGPASSWORD=url.password or '')
    result=subprocess.run([executable,'--format=custom','--file',str(backup),'--dbname',url.database],env=environment,capture_output=True,text=True,timeout=60)
    if result.returncode or not backup.is_file() or backup.stat().st_size==0:raise RuntimeError('Full live backup failed; migrations were not applied')
    env=os.environ.copy();env['DATABASE_URL']=url.render_as_string(hide_password=False)
    result=subprocess.run([sys.executable,'-m','alembic','upgrade','f1b2c3d4e5f6'],cwd=ROOT/'backend',env=env,capture_output=True,text=True,timeout=45)
    await db.reload_schema_state()
    after=await db.fetchval('SELECT version_num FROM alembic_version')
    new_artifacts={str(r['artifact_id']):r['content_hash'] for r in await db.fetch('SELECT artifact_id,content_hash FROM artifacts')}
    after_counts={name:await db.fetchval('SELECT count(*) FROM '+name) for name in counts}
    preserved=all(new_artifacts.get(key)==value for key,value in old_artifacts.items()) and all(after_counts[k]>=v for k,v in counts.items())
    await db.close()
    evidence={'status':'PASS' if result.returncode==0 and after=='f1b2c3d4e5f6' and preserved else 'BLOCKED',
        'from_revision':before,'to_revision':after,'migration_exit_code':result.returncode,
        'steps':[line for line in result.stderr.splitlines() if 'Running upgrade' in line],
        'backup':str(backup.relative_to(ROOT)),'backup_sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),
        'historical_artifact_hashes_preserved':preserved,'counts_before':counts,'counts_after':after_counts}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as output:json.dump(evidence,output,indent=2)
    print(json.dumps(evidence));return 0 if evidence['status']=='PASS' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    raise SystemExit(asyncio.run(main(parser.parse_args())))
