"""Explicit, bounded live OpenAI gateway acceptance with a persistent test ledger.

Uses the already authorized configured key. Never approves a production gate or
claims that this isolated provider check is a complete W09 modernization run.
"""
import argparse
import asyncio
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))


async def main(args):
    from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
    from app.core.config import settings
    from app.models.model_gateway import ModelGatewayBudget,ModelGatewayRequest
    from app.services import model_request_ledger as ledger
    from app.services.model_gateway import build_default_gateway,ModelGatewayError
    from app.schemas.phase6 import ChangeSet
    from app.services.phase6_workspace import safe_target
    if args.output.exists() or args.ledger.exists():raise ValueError('Acceptance evidence must not be overwritten')
    if settings.PHASE6_MODEL_PROVIDER!='openai' or settings.PHASE6_MODEL_IDENTIFIER!='gpt-4o-mini':
        raise ValueError('This bounded acceptance profile requires the configured openai/gpt-4o-mini selection')
    if not settings.OPENAI_API_KEY:raise ValueError('Configured OpenAI key is unavailable')
    if 'test' not in args.ledger.name:raise ValueError('An isolated test ledger path is required')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.ledger.parent.mkdir(parents=True,exist_ok=True)
    engine=create_async_engine('sqlite+aiosqlite:///'+str(args.ledger.resolve()))
    factory=async_sessionmaker(engine,expire_on_commit=False)
    async with engine.begin() as db:
        await db.run_sync(ModelGatewayBudget.__table__.create)
        await db.run_sync(ModelGatewayRequest.__table__.create)
    async with factory.begin() as db:
        db.add(ModelGatewayBudget(budget_id=1,ceiling_usd=Decimal('.01'),spent_usd=0,reserved_usd=0))
    ledger.AsyncSessionLocal=factory
    settings.REAL_MODEL_SANDBOX_ENABLED=True
    settings.MAX_BUDGET_USD=.01
    request_id='w09-test-'+uuid.uuid4().hex
    request={'request_id':request_id,'prompt_revision':'w09-isolated-bounded-changeset-v1','max_tokens':256,
        'temperature':0,'response_format':{'type':'json_object'},
        'prompt':'Generate a JSON ChangeSet only with keys files, design_notes, assumptions, test_commands. '
            'files must contain exactly modern/calc.py implementing typed Python add(x:int,y:int)->int returning x+y. '
            'Use an empty list for assumptions and test_commands and a short design_notes string. No other files.'}
    gateway=build_default_gateway();gateway.timeout_seconds=45
    evidence={'scope':'Configured OpenAI key; isolated persistent test ledger. No production gate decision, job conversion, or ZIP acceptance is claimed.',
        'request_id':request_id,'requested_provider':settings.PHASE6_MODEL_PROVIDER,'requested_model':settings.PHASE6_MODEL_IDENTIFIER,
        'maximum_output_tokens':256,'request_budget_usd':.01,'automatic_retries':0,
        'documentation':'https://developers.openai.com/api/docs/models/gpt-4o-mini'}
    try:
        result=await gateway.complete(provider='openai',model=settings.PHASE6_MODEL_IDENTIFIER,request=request,max_retries=0,max_cost_usd=.01)
        response=result.response
        changes=ChangeSet.model_validate(json.loads(response.output['content']))
        if set(changes.files)!={'modern/calc.py'}:raise ValueError('Provider exceeded the bounded ChangeSet scope')
        for name in changes.files:safe_target(args.output.parent,name,'modern')
        evidence.update(status='PASS',actual_model=response.provider_metadata.get('actual_model'),provider_request_id=response.provider_request_id,
            usage=response.usage.model_dump(),provider_metadata=response.provider_metadata,changeset=changes.model_dump(),
            changeset_sha256=hashlib.sha256(json.dumps(changes.model_dump(),sort_keys=True).encode()).hexdigest())
    except Exception as exc:
        # Do not serialize provider response bodies, environment or credentials.
        evidence.update(status='BLOCKED',failure_type=type(exc).__name__)
    async with factory() as db:
        row=await db.get(ModelGatewayRequest,request_id);budget=await db.get(ModelGatewayBudget,1)
        evidence['ledger']={k:str(getattr(row,k)) if getattr(row,k) is not None else None for k in (
            'status','requested_model','actual_model','provider_request_id','reserved_usd','estimated_cost_usd','billed_cost_usd',
            'input_tokens','output_tokens','attempt_count','rate_limit_count','last_error_type','started_at','finished_at')}
        evidence['budget']={k:str(getattr(budget,k)) for k in ('ceiling_usd','reserved_usd','spent_usd')}
    try:
        await ledger.PersistentModelRequestLedger().reserve(request_id=request_id,provider='openai',model=settings.PHASE6_MODEL_IDENTIFIER,
            prompt_revision='duplicate-probe',amount_usd=.01,ceiling_usd=.01)
        evidence['duplicate_dispatch_blocked']=False
    except ModelGatewayError:evidence['duplicate_dispatch_blocked']=True
    try:
        await ledger.PersistentModelRequestLedger().reserve(request_id='over-cap-'+uuid.uuid4().hex,provider='openai',model=settings.PHASE6_MODEL_IDENTIFIER,
            prompt_revision='budget-probe',amount_usd=.02,ceiling_usd=100)
        evidence['over_ceiling_reservation_blocked']=False
    except ModelGatewayError:evidence['over_ceiling_reservation_blocked']=True
    await engine.dispose()
    # A new interpreter reads committed accounting without dispatching anything.
    recovery=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--recover',str(args.ledger.resolve()),'--request-id',request_id],
        capture_output=True,text=True,timeout=15,cwd=ROOT/'backend')
    evidence['persistent_recovery']=json.loads(recovery.stdout) if recovery.returncode==0 else {'status':'BLOCKED'}
    with args.output.open('x') as output:json.dump(evidence,output,indent=2,default=str)
    print(json.dumps({k:evidence[k] for k in ('status','request_id','ledger','budget','duplicate_dispatch_blocked','over_ceiling_reservation_blocked','persistent_recovery')}))
    return 0 if evidence['status']=='PASS' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);parser.add_argument('--ledger',type=Path)
    parser.add_argument('--recover',type=Path);parser.add_argument('--request-id')
    args=parser.parse_args()
    if args.recover:
        import sqlite3
        with sqlite3.connect(args.recover.as_uri()+'?mode=ro',uri=True) as db:
            row=db.execute('SELECT status,actual_model,provider_request_id FROM model_gateway_requests WHERE request_id=?',(args.request_id,)).fetchone()
            print(json.dumps({'status':row[0],'actual_model':row[1],'provider_request_id':row[2]}))
    else:
        if not args.output or not args.ledger:parser.error('--output and --ledger required')
        sys.exit(asyncio.run(main(args)))
