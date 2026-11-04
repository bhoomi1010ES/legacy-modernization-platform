"""Actual separate controller + persistent VerificationRun acceptance on safe fixtures.

This tests verification components. It does not approve human gates or claim a
complete customer conversion, dependency/license audit or ZIP delivery.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))


async def main(args):
    from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
    from app.core.config import settings
    from app.models import Base
    from app.models.user import User
    from app.models.job import Job
    from app.models.module import Module,ModuleAttempt,VerificationRun
    from app.models.agent import AgentRun
    from app.services.durable_verification import prepare_and_execute
    from app.services.phase5_engine import digest
    from app.models.base import utc_now
    if args.output.exists() or args.database.exists():raise ValueError('Acceptance evidence must not be overwritten')
    if 'test' not in args.database.name:raise ValueError('A persistent isolated test database is required')
    provider=json.loads((ROOT/'docs/audits/W09_PROVIDER_20261102.json').read_text())
    if provider['status']!='PASS' or provider['ledger']['status']!='COMPLETED':raise ValueError('Actual completed provider evidence is required')
    # A named fixture profile scoped to this component test, never a global app
    # or PHP/Node/browser profile. The production image, scanner and I/O policy
    # remain enforced by the deployed controller; no Docker calls are mocked.
    specs=[{'category':'build','command':['python','-m','compileall','-q','.']},
        {'category':'unit','command':['python','-m','pytest','/acceptance/test_calc.py','-q']},
        {'category':'integration','command':['python','-m','pytest','/acceptance/test_integration.py','-q']},
        {'category':'static','command':['python','-m','mypy','--cache-dir=/tmp/mypy-cache','modern']},
        {'category':'security','command':['python','-m','bandit','-r','modern','-q']},
        {'category':'dependency','command':['pip-audit','--strict']},
        {'category':'license','command':['licensecheck','--fail-on','GPL']},
        {'category':'runtime','command':['python','-m','pytest','/acceptance/test_runtime.py','-q']},
        {'category':'api_compatibility','command':['python','-m','pytest','/acceptance/test_api_compatibility.py','-q']}]
    system_specs=[{'category':'build','command':['python','-m','compileall','-q','.']},
        {'category':'unit','command':['python','-m','pytest','/acceptance/test_calc.py','-q']},
        {'category':'integration','command':['python','-m','pytest','/acceptance/test_integration.py','-q']},
        {'category':'static','command':['python','-m','mypy','--cache-dir=/tmp/mypy-cache','modern']},
        {'category':'security','command':['python','-m','bandit','-r','modern','-q']},
        {'category':'dependency','command':['pip-audit','--strict']},
        {'category':'license','command':['licensecheck','--fail-on','GPL']},
        {'category':'runtime','command':['python','-m','pytest','/acceptance/test_runtime.py','-q']},
        {'category':'api_compatibility','command':['python','-m','pytest','/acceptance/test_api_compatibility.py','-q']}]
    settings.PHASE6_TARGET_PROFILES_JSON=json.dumps({'Python calculator fixture':{
        'version':'calculator-component-v1','image':settings.PHASE6_SANDBOX_IMAGE,
        'runtime':settings.SANDBOX_RUNTIME,'timeout':settings.PHASE6_SANDBOX_TIMEOUT,
        'adapter':['python','/adapter.py'],'checks':specs,'system_checks':system_specs}})
    args.database.parent.mkdir(parents=True,exist_ok=True)
    engine=create_async_engine('sqlite+aiosqlite:///'+str(args.database.resolve()))
    async with engine.begin() as db:await db.run_sync(Base.metadata.create_all)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    results=[]
    async with factory() as db:
        user=User(email='w09-verifier-isolated@example.test',full_name='Isolated verifier fixture',password_hash='disabled-account',role='DEVELOPER')
        db.add(user);await db.flush()
        job=Job(name='W09 isolated verifier components',source_repository='fixture://approved-calculator',source_stack='Python calculator fixture',
            target_stack='Python calculator fixture',owner_user_id=user.user_id,status='CREATED')
        db.add(job);await db.flush()
        module=Module(job_id=job.job_id,name='calculator-component-fixture',legacy_path='legacy',target_path='modern')
        db.add(module);await db.commit()
        good=provider['changeset']['files']
        fixtures=[('real-provider-correct',good,'add',True),
            ('build-passes-unit-fails',{'modern/calc.py':'def add(x: int, y: int) -> int:\n    return x-y\n'},'add',False),
            ('unit-passes-security-fails',{'modern/calc.py':'def add(x: int, y: int) -> int:\n    return x+y\n\ndef unsafe(command: str):\n    return eval(command)\n'},'add',False),
            ('unsupported-flow-is-unobserved',good,'unsupported-dom-navigation',False)]
        for number,(label,files,scenario,expected) in enumerate(fixtures,1):
            writer=AgentRun(job_id=job.job_id,agent_name='CodeWriter',task_id='component-'+uuid.uuid4().hex,
                model_provider='openai' if number==1 else 'seeded-negative-fixture',model_identifier=provider['actual_model'] if number==1 else 'NONE',status='SUCCEEDED',
                task_payload={'fixture':label,'provider_request_id':provider['provider_request_id'] if number==1 else None},output_payload={'files':files})
            db.add(writer);await db.flush()
            attempt=ModuleAttempt(module_id=module.module_id,agent_run_id=writer.run_id,attempt_number=number,status='GENERATED',git_branch='fixture/no-git-operations')
            db.add(attempt);await db.commit()
            cases=[{'test_case_id':'calculator-case','name':scenario,'fixtures':{'x':1,'y':2},'expected':3,'side_effects':{'count':1},'normalization':[]}]
            inputs={'files':files,'cases':cases,'baseline_hash':digest({'calculator-contract-v1':True}),
                'candidate_hash':digest(files),'suite_hash':digest(cases),'profile_version':'calculator-component-v1'}
            result,record,verifier=await prepare_and_execute(db,job,inputs,attempt_id=attempt.attempt_id,
                codewriter_worker_id='isolated-codewriter-fixture')
            record.status='PASS' if result.get('passed') else 'FAIL' if result.get('available') else 'BLOCKED'
            record.finished_at=utc_now();record.evidence={'verification':result,'scope':'Calculator fixture only; dependency/license/schema/browser checks are outside this component acceptance'}
            record.evidence_hash=digest(record.evidence)
            verifier.status='SUCCEEDED' if result.get('passed') else 'FAILED';verifier.completed_at=record.finished_at
            verifier.output_payload=result
            await db.commit()
            entry={'fixture':label,'expected_verification_pass':expected,'actual_verification_pass':result.get('passed') is True,
                'verification_run_id':str(record.verification_run_id),'agent_run_id':str(verifier.run_id),'codewriter_run_id':str(writer.run_id),
                'worker_id':record.worker_id,'lease_token':record.lease_token,'candidate_hash':record.candidate_hash,'suite_hash':record.suite_hash,
                'evidence_hash':record.evidence_hash,'result':result}
            entry['status']='PASS' if entry['actual_verification_pass']==expected and record.worker_id and verifier.run_id!=writer.run_id else 'FAIL'
            results.append(entry)
            print(json.dumps({'fixture':label,'status':entry['status'],'verification_status':record.status,'worker_id':record.worker_id,
                'reason':result.get('reason'),'checks':[(c['category'],c['status']) for c in result.get('checks',[])]}),flush=True)
    await engine.dispose()
    # Reopen the actual persistent DB and verify immutable terminal bindings.
    engine=create_async_engine('sqlite+aiosqlite:///'+str(args.database.resolve()));factory=async_sessionmaker(engine,expire_on_commit=False)
    async with factory() as db:
        persistent=True
        for entry in results:
            record=await db.get(VerificationRun,uuid.UUID(entry['verification_run_id']))
            persistent=persistent and record.evidence_hash==entry['evidence_hash'] and digest(record.evidence)==record.evidence_hash
        record.evidence={'fabricated':True}
        try:await db.commit();immutable=False
        except ValueError:immutable=True;await db.rollback()
    await engine.dispose()
    evidence={'scope':'Real deployed controller, real tools/scanner/I/O, real provider ChangeSet and isolated persistent VerificationRuns. No G1-G4 approvals or full W09 ZIP delivery claimed.',
        'runs':results,'persistent_evidence_recovered':bool(persistent),'terminal_evidence_rewrite_rejected':immutable,
        'provider_evidence_sha256':hashlib.sha256((ROOT/'docs/audits/W09_PROVIDER_20261102.json').read_bytes()).hexdigest(),
        'status':'PASS' if all(r['status']=='PASS' for r in results) and persistent and immutable else 'FAIL'}
    with args.output.open('x') as output:json.dump(evidence,output,indent=2,default=str)
    print(json.dumps({k:v for k,v in evidence.items() if k!='runs'}));return 0 if evidence['status']=='PASS' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--database',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    raise SystemExit(asyncio.run(main(parser.parse_args())))
