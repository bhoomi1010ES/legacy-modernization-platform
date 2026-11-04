"""Control-plane RPC client. Never imports Docker or executes repository code."""

import asyncio
import time
import uuid
from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.services.sandbox_protocol import digest, seal, unseal


async def rpc(payload):
    url=getattr(settings,'SANDBOX_CONTROLLER_URL','')
    parsed=urlsplit(url)
    if parsed.scheme not in {'http','https'} or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Sandbox controller URL is missing or invalid')
    if parsed.scheme=='http' and parsed.hostname not in {'127.0.0.1','localhost','::1'}:
        raise ValueError('Remote sandbox controllers require HTTPS')
    nonce=uuid.uuid4().hex
    envelope=seal({**payload,'nonce':nonce,'expires_at':time.time()+120},getattr(settings,'SANDBOX_DISPATCH_KEY',''))
    async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=15) as client:
        response=await client.post(url.rstrip('/')+'/v1/rpc',json=envelope)
        response.raise_for_status()
        answer=unseal(response.json(),getattr(settings,'SANDBOX_ATTESTATION_KEY',''),expiring=False)
        if answer.get('rpc_nonce') != nonce:
            raise ValueError('Replayed or mismatched sandbox RPC response')
        return answer


async def health():
    info=await rpc({'action':'health','nonce':uuid.uuid4().hex,'runtime':settings.SANDBOX_RUNTIME})
    runtime=info.get('runtime') or {}
    if info.get('status')!='ready' or 'name=rootless' not in runtime.get('security_options',[]):
        raise ValueError('Independent sandbox controller/worker is not ready: '+str(info.get('blocked_reasons') or []))
    return info


async def execute(execution,binding):
    required={'request_id','job_id','attempt_id','candidate_hash','suite_hash'}
    if not binding or not required<=set(binding):
        raise ValueError('Exact durable verification/run and candidate/suite binding is required')
    scope={key:str(binding[key]) for key in required}
    request={**scope,'execution':execution}
    expected=digest(request)
    await rpc({**request,'action':'execute'})
    deadline=time.monotonic()+execution['timeout']+180
    try:
        while time.monotonic()<deadline:
            status=await rpc({**scope,'action':'status'})
            if status['status']=='SUCCEEDED':
                signed=status.get('result')
                result=unseal(signed,settings.SANDBOX_ATTESTATION_KEY,expiring=False)
                if result.get('input_hash')!=expected or any(result.get(k)!=v for k,v in scope.items()):
                    raise ValueError('Controller evidence belongs to different/stale inputs')
                if not result.get('worker_id') or not result.get('lease_token'):
                    raise ValueError('Controller evidence lacks an independently leased worker')
                return {**result,'attestation':signed}
            if status['status'] in {'CANCELLED','BLOCKED'}:
                failure=unseal(status['result'],settings.SANDBOX_ATTESTATION_KEY,expiring=False) if status.get('result') else {}
                raise ValueError(failure.get('reason') or 'Independent execution '+status['status'].lower())
            await asyncio.sleep(0.25)
        raise TimeoutError('Independent sandbox deadline exceeded')
    except BaseException:
        try:
            await asyncio.shield(rpc({**scope,'action':'cancel'}))
        except Exception:
            # Preserve the original failure. The durable controller deadline and
            # lease reaper still own cleanup when the network is unavailable.
            pass
        raise
