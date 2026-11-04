"""Synthetic signed controller replies for orchestration UNIT tests only.

These records never qualify as real sandbox/provider acceptance evidence.
"""
import time
from app.core.config import settings
from app.services.phase6_sandbox import assess
from app.services.sandbox_protocol import digest,seal


def synthetic_result(files,cases,checks,binding,profile,observations):
    now=time.time()
    test_categories={'unit','integration','runtime','api_compatibility','schema'}
    raw_checks=[{**item,'case_count':1 if item['category'] in test_categories else None,
        'tool_name':'SYNTHETIC_UNIT_TEST_ONLY','tool_version':'SYNTHETIC_UNIT_TEST_ONLY',
        'started_at':'2026-11-02T00:00:00+00:00','finished_at':'2026-11-02T00:00:01+00:00',
        'logs_hash':digest(item)} for item in checks]
    observation={'checks':raw_checks,'observations':observations,'source_unchanged':True}
    execution_input={**{k:profile[k] for k in ('image','runtime','checks','adapter','timeout')},'files':files,
        'cases':[{k:c[k] for k in ('test_case_id','name','fixtures')} for c in cases]}
    stage={'exit_code':0,'cleanup':{'container_absent':True},'started_at':now,'finished_at':now+1,
        'worker_id':'synthetic-unit-container','image_digest':profile['image']}
    review={'status':'PASS','findings':[],'worker_id':'synthetic-unit-reviewer'}
    proof={**binding,'execution_purpose':'VERIFICATION','input_hash':digest({**binding,'execution':execution_input}),
        'worker_id':'synthetic-unit-verifier','lease_token':'synthetic-unit-lease','lease_generation':1,'lease_expires_at':now+120,
        'preflight':stage,'execution':{**stage,'observation':observation},'review':{**stage,'observation':review},
        'image_scan':{'status':'PASS','tool':'SYNTHETIC_UNIT_TEST_ONLY'}}
    return {**assess(observation,cases,profile['checks'],digest(proof),image_digest=profile['image']),
        'runtime_evidence':proof['execution'],'independent_worker_id':proof['worker_id'],
        'controller_lease_token':proof['lease_token'],'controller_lease_generation':1,'controller_lease_expires_at':now+120,
        'controller_attestation':seal(proof,settings.SANDBOX_ATTESTATION_KEY),'independent_review':review,
        'image_id':profile['image'],'container_name':stage['worker_id']}
