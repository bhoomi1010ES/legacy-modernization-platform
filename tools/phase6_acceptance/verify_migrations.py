"""Test forward migrations against a schema clone in a fresh PostgreSQL database.

The live database is read only. Only the uniquely created test database is dropped.
No credential values or customer rows are copied into the evidence report.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))


async def main(args):
    import asyncpg
    from sqlalchemy.engine import make_url
    from app.core.config import settings
    from app.core.testing_infrastructure import IsolationGuard
    if args.output.exists():raise ValueError('Migration evidence must not be overwritten')
    url=make_url(settings.DATABASE_URL).set(host='127.0.0.1')
    name='rebase_test_w09_'+uuid.uuid4().hex
    test_url=url.set(database=name)
    IsolationGuard.verify_database_url(test_url.render_as_string(hide_password=False))
    def dsn(value):return value.set(drivername='postgresql').render_as_string(hide_password=False)
    bindir=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'PostgreSQL/18/bin'
    dump=shutil.which('pg_dump') or str(bindir/'pg_dump.exe')
    restore=shutil.which('pg_restore') or str(bindir/'pg_restore.exe')
    env=os.environ.copy();env.update(PGHOST=url.host,PGPORT=str(url.port or 5432),PGUSER=url.username or '',PGPASSWORD=url.password or '')
    created=False;admin=await asyncpg.connect(dsn(url));report={'scope':'Forward migration acceptance on a schema-only isolated PostgreSQL clone; live DB is read only.'}
    try:
        prior=await admin.fetchval('SELECT version_num FROM alembic_version')
        with tempfile.TemporaryDirectory(prefix='w09-test-migration-') as folder:
            archive=Path(folder)/'schema.dump'
            result=subprocess.run([dump,'--schema-only','--no-owner','--no-privileges','--format=custom','--file',str(archive),'--dbname',url.database],env=env,capture_output=True,text=True,timeout=30)
            if result.returncode:raise RuntimeError('Schema dump failed')
            await admin.execute('CREATE DATABASE "'+name+'"');created=True
            result=subprocess.run([restore,'--no-owner','--no-privileges','--exit-on-error','--dbname',name,str(archive)],env=env,capture_output=True,text=True,timeout=30)
            if result.returncode:raise RuntimeError('Isolated schema restore failed')
            db=await asyncpg.connect(dsn(test_url))
            try:
                await db.execute('INSERT INTO alembic_version(version_num) VALUES($1)',prior)
                await db.execute("INSERT INTO model_gateway_requests(request_id,provider,requested_model,prompt_revision,status,reserved_usd) VALUES('migration-history-probe','fixture','fixture','r1','UNKNOWN',.001)")
            finally:await db.close()
            migrate_env=os.environ.copy();migrate_env.update(DATABASE_URL=test_url.render_as_string(hide_password=False),ENVIRONMENT='testing')
            result=subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=ROOT/'backend',env=migrate_env,capture_output=True,text=True,timeout=45)
            report['migration_exit_code']=result.returncode
            report['migration_steps']=[line for line in result.stderr.splitlines() if 'Running upgrade' in line]
            if result.returncode:raise RuntimeError('Forward migrations failed on isolated PostgreSQL')
            db=await asyncpg.connect(dsn(test_url))
            try:
                revision=await db.fetchval('SELECT version_num FROM alembic_version')
                columns=[r['column_name'] for r in await db.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='verification_runs'")]
                row=dict(await db.fetchrow("SELECT status,reserved_usd,attempt_id,selection_hash,reconciliation_status,charged_cost_usd,released_usd FROM model_gateway_requests WHERE request_id='migration-history-probe'"))
                preserved=row['status']=='UNKNOWN' and float(row['reserved_usd'])==.001 and all(row[k] is None for k in ('attempt_id','selection_hash','reconciliation_status','charged_cost_usd','released_usd'))
                report.update(status='PASS' if preserved and 'candidate_hash' in columns and 'candidate_commit' not in columns and 'integration_run_id' in columns else 'FAIL',
                    from_revision=prior,to_revision=revision,historical_request_preserved=preserved,verification_columns=columns)
            finally:await db.close()
    except Exception as exc:report.update(status='BLOCKED',failure_type=type(exc).__name__,failure=str(exc) if isinstance(exc,RuntimeError) else 'Infrastructure or database authorization unavailable')
    finally:
        if created:
            # Only this exact, freshly created test DB can be removed.
            assert name.startswith('rebase_test_w09_') and name!=url.database
            await admin.execute('DROP DATABASE "'+name+'"')
            report['isolated_database_cleanup']=True
        await admin.close()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as output:json.dump(report,output,indent=2,default=str)
    print(json.dumps(report));return 0 if report['status']=='PASS' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    sys.exit(asyncio.run(main(parser.parse_args())))
