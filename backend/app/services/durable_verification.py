"""Persist immutable inputs before dispatch to independently leased controller workers."""

import uuid
from datetime import datetime, timezone
from app.models.agent import AgentRun
from app.models.module import VerificationRun
from app.services.phase5_engine import digest
from app.services import phase6_sandbox
from app.services.worker_dispatch_service import worker_dispatch_service


async def prepare_and_execute(db,job,inputs,*,attempt_id=None,integration_run_id=None,artifact_refs=None,codewriter_worker_id=None):
    from app.services.verification_profiles import get_profile
    target_profile=get_profile(job.target_stack)
    checks=inputs.get('system_checks') if integration_run_id else target_profile['checks']
    if not checks:
        raise ValueError('A complete target-stack verification profile is required')
    frozen_profile={
        'version':target_profile['version'],'image':target_profile['image'],
        'runtime':target_profile['runtime'],'timeout':target_profile['timeout'],
        'checks':checks,'adapter':target_profile['adapter'],
        'target_key':target_profile['target_key'],'system_checks':target_profile['system_checks'],
    }
    if inputs.get('execution_profile') is not None and inputs['execution_profile'] != frozen_profile:
        raise ValueError('Target verification profile changed after it was frozen')
    inputs={**inputs,'execution_profile':frozen_profile}
    inputs['profile_digest']=digest(frozen_profile)
    verifier=AgentRun(job_id=job.job_id,agent_name='Verifier',task_id='verification-'+uuid.uuid4().hex,
        model_provider='system',model_identifier=target_profile['version'],status='QUEUED',
        task_payload={**{k:inputs[k] for k in ('candidate_hash','suite_hash','profile_digest')},
            'inputs':inputs,'input_hash':digest(inputs),'codewriter_worker_id':codewriter_worker_id},
        input_artifact_refs=artifact_refs or [],trace_payload={'events':['QUEUED']})
    db.add(verifier);await db.flush()
    record=VerificationRun(attempt_id=attempt_id,integration_run_id=integration_run_id,agent_run_id=verifier.run_id,
        candidate_hash=inputs['candidate_hash'],suite_hash=inputs['suite_hash'],profile_version=target_profile['version'],
        profile_digest=inputs['profile_digest'],input_hash=digest(inputs),status='QUEUED',evidence={})
    db.add(record);await db.flush()
    verifier.task_payload={**verifier.task_payload,'controller_request_id':str(record.verification_run_id)}
    await db.commit()
    result=await dispatch(db,job,record,verifier)
    return result,record,verifier


async def dispatch(db,job,record,verifier):
    inputs=verifier.task_payload['inputs']
    if digest(inputs)!=record.input_hash:
        raise ValueError('Persisted verifier inputs were changed')
    binding={'request_id':str(record.verification_run_id),'job_id':str(job.job_id),
        'attempt_id':str(record.attempt_id or record.integration_run_id),'candidate_hash':record.candidate_hash,'suite_hash':record.suite_hash}
    result=await phase6_sandbox.execute(inputs['files'],inputs['cases'],inputs['baseline_hash'],
        system_checks=inputs.get('system_checks'),binding=binding,frozen_profile=inputs['execution_profile'])
    result.update(verification_run_id=str(record.verification_run_id),candidate_hash=record.candidate_hash,suite_hash=record.suite_hash)
    worker=result.get('independent_worker_id')
    if worker:
        record.worker_id=worker;record.lease_token=result['controller_lease_token'];record.status='RUNNING'
        record.started_at=datetime.fromtimestamp(result['runtime_evidence']['started_at'],timezone.utc)
        record.lease_expires_at=datetime.fromtimestamp(result['controller_lease_expires_at'],timezone.utc)
        verifier.status='RUNNING';verifier.started_at=record.started_at
        verifier.trace_payload={'events':['QUEUED','INDEPENDENTLY_LEASED','EXECUTED'],'worker_id':worker,
            'controller_lease_generation':result['controller_lease_generation']}
        await worker_dispatch_service.register_worker(db,worker,'VERIFIER',version=record.profile_version,metadata_payload={'controller_attested':True})
    remote_review=result.get('independent_review') or {'status':'BLOCKED','findings':[],'worker_id':None}
    if remote_review is not None:
        reviewer=AgentRun(job_id=job.job_id,agent_name='Reviewer',task_id='review-'+uuid.uuid4().hex,
            model_provider='system',model_identifier='w09-independent-review-v1',
            status='SUCCEEDED' if remote_review['status']=='PASS' else 'FAILED',
            task_payload={'candidate_hash':record.candidate_hash,'suite_hash':record.suite_hash,
                'verification_run_id':str(record.verification_run_id),'controller_request_id':str(record.verification_run_id)},
            trace_payload={'worker_id':remote_review.get('worker_id'),'events':['INDEPENDENT_REVIEW_EXECUTED']},
            output_payload=remote_review,completed_at=datetime.now(timezone.utc))
        db.add(reviewer);await db.flush()
        result['reviewer_agent_run_id']=str(reviewer.run_id)
    await db.commit()
    return result
