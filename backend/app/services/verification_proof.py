"""Re-assess controller observations against frozen, server-owned inputs."""
from app.core.config import settings
from app.services.sandbox_protocol import unseal, digest


def validate_success(payload, producer, job_id, *, reviewer=False):
    proof=unseal(payload.get('controller_attestation'),settings.SANDBOX_ATTESTATION_KEY,expiring=False)
    if proof.get('execution_purpose')!='VERIFICATION':
        raise ValueError('Diagnostic execution cannot authorize verification or delivery')
    expected=producer.task_payload
    if any(proof.get(k)!=expected.get(k) for k in ('candidate_hash','suite_hash')) or proof.get('request_id')!=expected.get('controller_request_id'):
        raise ValueError('Wrong candidate, frozen suite or independent execution')
    if proof.get('job_id')!=str(job_id) or not proof.get('worker_id') or not proof.get('lease_token'):
        raise ValueError('Independent worker lease is missing')
    for stage in ('preflight','execution','review'):
        if proof[stage].get('exit_code')!=0 or not proof[stage].get('cleanup',{}).get('container_absent'):
            raise ValueError('Independent execution or cleanup failed')
    if proof['review']['observation']['status']!='PASS' or proof['image_scan']['status']!='PASS':
        raise ValueError('Independent reviewer or image scan did not pass')
    if not reviewer:
        from app.services.phase6_sandbox import assess
        inputs=expected['inputs'];profile=inputs['execution_profile']
        if digest(inputs)!=expected['input_hash']:
            raise ValueError('Frozen verifier inputs were modified')
        execution={**{k:profile[k] for k in ('image','runtime','checks','adapter','timeout')},
            'files':inputs['files'],'cases':[{k:c[k] for k in ('test_case_id','name','fixtures')} for c in inputs['cases']]}
        scope={k:proof[k] for k in ('request_id','job_id','attempt_id','candidate_hash','suite_hash')}
        if proof['input_hash']!=digest({**scope,'execution':execution}):
            raise ValueError('Controller observations belong to different frozen inputs')
        assessment=assess(proof['execution']['observation'],inputs['cases'],profile['checks'],proof['input_hash'],image_digest=profile['image'])
        if not assessment['passed']:
            raise ValueError('Actual checks or frozen characterization failed')
    return proof
