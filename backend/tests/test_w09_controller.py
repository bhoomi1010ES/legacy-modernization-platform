"""Security regressions. Real-container acceptance is recorded separately, not mocked here."""
import base64
import hashlib
import json
import time
from types import SimpleNamespace
import uuid

import pytest
from starlette.responses import Response
from app.services.sandbox_protocol import seal,unseal,validate_execution,validate_check_profile
from app.services import phase6_sandbox,phase6_workspace
from app.services.artifact_service import ArtifactService
from app.core.errors import ForbiddenException


def test_signed_execution_rejects_modified_scope_and_expired_capability():
    key='dispatch-key-'+('a'*48)
    message=seal({'job_id':'j','expires_at':time.time()+30},key)
    assert unseal(message,key)['job_id']=='j'
    message['payload']['job_id']='other-tenant'
    with pytest.raises(ValueError,match='signature'):unseal(message,key)
    with pytest.raises(ValueError,match='expired'):
        unseal(seal({'expires_at':time.time()-1},key),key)


def test_registered_runsc_flag_cannot_make_a_rootful_daemon_rootless(monkeypatch):
    from app.services import sandbox_controller as controller
    info={'SecurityOptions':['name=seccomp,profile=builtin'],
        'Runtimes':{'runsc':{'dev.gvisor.flag.rootless':'false'}},'ServerVersion':'test'}
    monkeypatch.setattr(controller,'docker',lambda *args:SimpleNamespace(returncode=0,stdout=json.dumps(info)))
    with pytest.raises(ValueError,match='rootless'):controller.runtime_evidence('docker-rootless')


@pytest.mark.parametrize('category,command',[('unit',['python','-m','compileall','.']),('unit',['python','-c','print(1)']),('security',['npm','install'])])
def test_execution_policy_rejects_false_unit_or_install_profiles(category,command):
    image='sha256:'+'a'*64
    request={k:'fixture' for k in ('request_id','job_id','attempt_id','candidate_hash','suite_hash')}
    request['execution']={'image':image,'runtime':'docker-rootless','timeout':30,'files':{},
        'adapter':['python','/adapter.py'],'checks':[{'category':category,'command':command}]}
    with pytest.raises(ValueError):validate_execution(request,{image})


def test_target_verification_profile_rejects_missing_categories_and_mislabeled_compile():
    incomplete=[
        {"category":"build","command":["python","-m","compileall","-q","."]},
        {"category":"unit","command":["python","-m","pytest","-q","tests/unit"]},
        {"category":"integration","command":["python","-m","compileall","-q","."]},
        {"category":"static","command":["python","-m","mypy","app"]},
        {"category":"security","command":["python","-m","bandit","-r","app"]},
    ]
    assert not validate_check_profile(incomplete,system=True)
    assert not validate_check_profile(incomplete,system=False)


def test_target_verification_profile_requires_distinct_real_check_categories():
    profile=[
        {"category":"build","command":["python","-m","compileall","-q","."]},
        {"category":"unit","command":["python","-m","pytest","-q","tests/unit"]},
        {"category":"integration","command":["python","-m","pytest","-q","tests/integration"]},
        {"category":"static","command":["python","-m","mypy","app"]},
        {"category":"security","command":["python","-m","bandit","-r","app"]},
        {"category":"dependency","command":["pip-audit","--strict"]},
        {"category":"license","command":["licensecheck","--fail-on","GPL"]},
        {"category":"runtime","command":["python","-m","pytest","-q","tests/runtime"]},
        {"category":"api_compatibility","command":["python","-m","pytest","-q","tests/api_compatibility"]},
    ]
    assert validate_check_profile(profile,system=True)
    profile[2]={**profile[2],"command":["python","-m","compileall","-q","."]}
    assert not validate_check_profile(profile,system=True)


def test_target_stack_profile_has_exact_version_image_and_frozen_digest(monkeypatch):
    from app.core.config import settings
    from app.services.verification_profiles import get_profile
    checks=[
        {"category":"build","command":["python","-m","compileall","-q","."]},
        {"category":"unit","command":["python","-m","pytest","-q","tests/unit"]},
        {"category":"integration","command":["python","-m","pytest","-q","tests/integration"]},
        {"category":"static","command":["python","-m","mypy","app"]},
        {"category":"security","command":["python","-m","bandit","-r","app"]},
        {"category":"dependency","command":["pip-audit","--strict"]},
        {"category":"license","command":["licensecheck","--fail-on","GPL"]},
        {"category":"runtime","command":["python","-m","pytest","-q","tests/runtime"]},
        {"category":"api_compatibility","command":["python","-m","pytest","-q","tests/api_compatibility"]},
    ]
    system_checks=[dict(check) for check in checks]
    profile={"version":"php-node-profile-v1","image":"sha256:"+"a"*64,
        "runtime":"docker-rootless","timeout":120,"adapter":["python","/adapter.py"],
        "checks":checks,"system_checks":system_checks}
    monkeypatch.setattr(settings,"PHASE6_TARGET_PROFILES_JSON",json.dumps({"PHP 8 / Node 22":profile}))
    loaded=get_profile("  php   8 / NODE 22 ")
    assert loaded["version"]=="php-node-profile-v1" and loaded["image"]==profile["image"]
    assert len(loaded["profile_digest"])==64
    with pytest.raises(ValueError,match="No unique versioned"):
        get_profile("PHP 8")


def test_verifier_never_uses_generic_profile_fallback(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings,"PHASE6_TARGET_PROFILES_JSON","{}")
    with pytest.raises(ValueError,match="exact job target stack"):
        phase6_sandbox.configuration()
    with pytest.raises(ValueError,match="No unique versioned"):
        phase6_sandbox.configuration("PHP")


@pytest.mark.parametrize('category',['unit','integration','runtime','api_compatibility','schema'])
def test_zero_executed_test_cases_do_not_pass(category):
    spec={'category':category,'command':['python','-m','pytest']}
    data={'checks':[{**spec,'duration_ms':1,'exit_code':0,'case_count':0}], 'observations':[],'source_unchanged':True}
    result=phase6_sandbox.assess(data,[],[spec],'candidate',image_digest='sha256:'+'a'*64)
    assert result['checks'][0]['status']=='NOT_RUN'
    assert result['checks'][0]['image_digest']=='sha256:'+'a'*64
    assert result['passed'] is False


@pytest.mark.asyncio
async def test_binary_snapshot_preserves_actual_bytes_and_hash(tmp_path):
    await phase6_workspace.git(tmp_path,'init')
    raw=b'\x89PNG\xff\x00binary-fixture'
    (tmp_path/'asset.png').write_bytes(raw)
    await phase6_workspace.git(tmp_path,'add','--','asset.png')
    snapshot=await phase6_workspace.file_snapshot(tmp_path)
    asset=snapshot['asset.png']
    assert base64.b64decode(asset['data'],validate=True)==raw
    assert asset['sha256']==hashlib.sha256(raw).hexdigest()


@pytest.mark.asyncio
async def test_snapshot_omits_only_explicit_exact_path(tmp_path):
    await phase6_workspace.git(tmp_path,'init')
    (tmp_path/'bin').mkdir()
    (tmp_path/'bin'/'main').write_bytes(b'compiled-executable')
    (tmp_path/'main.go').write_text('package main\n')
    await phase6_workspace.git(tmp_path,'add','--','bin/main','main.go')
    snapshot=await phase6_workspace.file_snapshot(tmp_path,exclude_paths={'bin/main'})
    assert set(snapshot)=={'main.go'}
    assert (tmp_path/'bin'/'main').read_bytes()==b'compiled-executable'


@pytest.mark.asyncio
async def test_snapshot_rejects_noncanonical_exclusion_path(tmp_path):
    with pytest.raises(ValueError,match='Invalid exact snapshot exclusion path'):
        await phase6_workspace.file_snapshot(tmp_path,exclude_paths={'bin/../outside'})


@pytest.mark.asyncio
async def test_verification_label_without_independent_run_is_rejected():
    with pytest.raises(ForbiddenException,match='persisted producer'):
        await ArtifactService().publish_artifact(None,uuid.uuid4(),'VerificationReport',1,b'{"passed":true}','Verifier')


@pytest.mark.asyncio
async def test_codewriter_run_cannot_publish_verification_under_verifier_label():
    job_id=uuid.uuid4()
    class Session:
        async def get(self,*args):return SimpleNamespace(job_id=job_id,agent_name='CodeWriter')
    with pytest.raises(ForbiddenException,match='identity'):
        await ArtifactService().publish_artifact(Session(),job_id,'VerificationReport',1,b'{"passed":true}','Verifier',producer_run_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_readiness_reports_missing_controller_unavailable(monkeypatch):
    from app.api.v1 import system
    from app.core.config import settings
    async def healthy_database():return True
    monkeypatch.setattr(system,'ping_database',healthy_database)
    monkeypatch.setattr(settings,'SANDBOX_CONTROLLER_URL','')
    response=Response()
    readiness=await system.get_readiness(response)
    assert readiness.ready is False
    assert readiness.components['sandboxes']=='unavailable'
    assert response.status_code==503


def test_cleanup_reclaims_expired_controller_lease(tmp_path,monkeypatch):
    from app.services import sandbox_controller as controller
    path=str(tmp_path/'execution_test.sqlite')
    controller.initialize(path)
    with controller.connect(path) as db:
        db.execute('INSERT INTO executions(request_id,job_id,attempt_id,input_hash,payload,status,lease_expires) VALUES(?,?,?,?,?,?,?)',
            ('old','job','attempt','hash','{}','RUNNING',time.time()-5))
    monkeypatch.setattr(controller,'docker',lambda *args:SimpleNamespace(returncode=0,stdout=''))
    controller.garbage_collect(path)
    with controller.connect(path) as db:
        assert db.execute('SELECT status FROM executions WHERE request_id=?',('old',)).fetchone()['status']=='BLOCKED'


def test_controller_sqlite_handles_close_after_every_transaction(tmp_path):
    import sqlite3
    from app.services import sandbox_controller as controller
    path=str(tmp_path/'queue_test.sqlite')
    controller.initialize(path)
    for _ in range(300):
        with controller.connect(path) as db:
            assert db.execute('SELECT count(*) FROM executions').fetchone()[0]==0
        with pytest.raises(sqlite3.ProgrammingError,match='closed'):
            db.execute('SELECT 1')


@pytest.mark.asyncio
async def test_concurrent_persistent_reservations_cannot_raise_or_exceed_cap(tmp_path,monkeypatch):
    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker,create_async_engine
    from app.models.model_gateway import ModelGatewayBudget,ModelGatewayRequest
    from app.services import model_request_ledger as ledger
    from app.services.model_gateway import ModelGatewayError
    engine=create_async_engine('sqlite+aiosqlite:///'+str(tmp_path/'test_budget.sqlite'))
    async with engine.begin() as connection:
        await connection.run_sync(ModelGatewayBudget.__table__.create)
        await connection.run_sync(ModelGatewayRequest.__table__.create)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    monkeypatch.setattr(ledger,'AsyncSessionLocal',factory)
    async with factory.begin() as db:
        db.add(ModelGatewayBudget(budget_id=1,ceiling_usd=.1,reserved_usd=0,spent_usd=0))
    async def reserve(i):
        try:
            await ledger.model_request_ledger.reserve(request_id=str(i),provider='openai',model='fixture',prompt_revision='r1',amount_usd=.06,ceiling_usd=100)
            return True
        except ModelGatewayError:return False
    try:
        results=await asyncio.gather(*(reserve(i) for i in range(6)))
        assert sum(results)==1
        async with factory() as db:
            budget=await db.get(ModelGatewayBudget,1)
            assert float(budget.reserved_usd)==pytest.approx(.06)
            assert float(budget.ceiling_usd)==pytest.approx(.1)
        winner=str(results.index(True))
        await ledger.model_request_ledger.begin_attempt(winner)
        with pytest.raises(ModelGatewayError,match='not dispatchable'):
            await ledger.model_request_ledger.begin_attempt(winner)
        for invalid in (float('nan'),float('inf'),-.1):
            with pytest.raises(ModelGatewayError):
                await ledger.model_request_ledger.reserve(request_id='invalid',provider='openai',model='fixture',prompt_revision='r1',amount_usd=invalid,ceiling_usd=.1)
    finally:await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('ready,current,selected',[(False,True,True),(True,False,True),(True,True,False)])
async def test_delivery_download_rejects_pending_g4_stale_or_other_package(monkeypatch,ready,current,selected):
    from app.api.v1.artifacts import _authorize_delivery_download
    from app.services import phase7_service
    from app.core.errors import ConflictException
    artifact=SimpleNamespace(artifact_id=uuid.uuid4(),artifact_type='MODERNIZED_PROJECT_ZIP',media_type='application/zip')
    async def delivery(db,job):
        return {'delivery_ready':ready,'package_current':current,'delivery_zip':{'artifact_id':str(artifact.artifact_id) if selected else str(uuid.uuid4())}}
    monkeypatch.setattr(phase7_service,'delivery',delivery)
    with pytest.raises(ConflictException):
        await _authorize_delivery_download(None,None,artifact)


@pytest.mark.asyncio
async def test_delivery_download_accepts_only_exact_approved_zip_and_manifest(monkeypatch):
    from app.api.v1.artifacts import _authorize_delivery_download
    from app.services import phase7_service
    zip_id,manifest_id=uuid.uuid4(),uuid.uuid4()
    async def delivery(db,job):
        return {'delivery_ready':True,'package_current':True,'delivery_zip':{'artifact_id':str(zip_id),'manifest_artifact_id':str(manifest_id)}}
    monkeypatch.setattr(phase7_service,'delivery',delivery)
    for key,kind,media in [(zip_id,'MODERNIZED_PROJECT_ZIP','application/zip'),(manifest_id,'MODERNIZATION_MANIFEST','application/json')]:
        await _authorize_delivery_download(None,None,SimpleNamespace(artifact_id=key,artifact_type=kind,media_type=media))


def test_artifact_public_schema_contains_no_storage_location():
    from app.schemas.artifacts import ArtifactResponse
    assert 'storage_path' not in ArtifactResponse.model_fields
