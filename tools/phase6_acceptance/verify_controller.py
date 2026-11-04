"""Real standalone-controller regression probes; never claims full W09 acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[2]
SERVICES=ROOT/'backend/app/services'
sys.path.insert(0,str(SERVICES))
from sandbox_protocol import canonical,digest,seal,unseal


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--image',required=True);parser.add_argument('--old-image',required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--provider-evidence',type=Path);args=parser.parse_args()
    if args.output.exists():raise ValueError('Evidence must not be overwritten')
    dispatch=secrets.token_hex(32);attestation=secrets.token_hex(32)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    def rpc(body):
        request=urllib.request.Request('http://127.0.0.1:'+str(port)+'/v1/rpc',data=canonical(seal({**body,'expires_at':time.time()+120},dispatch)),headers={'Content-Type':'application/json'},method='POST')
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=10) as response:
            return unseal(json.load(response),attestation,expiring=False)
    reports=[];server=None
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rebase-w09-controller-test-') as folder:
        environment={k:v for k,v in os.environ.items() if k in {'PATH','HOME','XDG_RUNTIME_DIR','LANG','LC_ALL'}}
        environment.update(DOCKER_CONTEXT='rootless',SANDBOX_ALLOW_DIAGNOSTICS='1',SANDBOX_DISPATCH_KEY=dispatch,SANDBOX_ATTESTATION_KEY=attestation,
            SANDBOX_ALLOWED_IMAGES=json.dumps([args.image,args.old_image]),
            SANDBOX_ALLOWED_ADAPTER_HASHES=json.dumps([hashlib.sha256((ROOT/'tools/phase6_acceptance/image/adapter.py').read_bytes()).hexdigest()]))
        log=open(Path(folder)/'controller.log','w+')
        def start():
            return subprocess.Popen([sys.executable,str(SERVICES/'sandbox_controller.py'),'--port',str(port),'--state',str(Path(folder)/'execution_test.sqlite')],env=environment,stdout=log,stderr=log)
        server=start()
        try:
            deadline=time.time()+15
            while True:
                try:health=rpc({'action':'health','runtime':'docker-rootless'});break
                except Exception:
                    if time.time()>deadline:raise RuntimeError('Controller did not start')
                    time.sleep(0.2)
            specs=[{'category':'build','command':['python','-m','compileall','-q','.']},
                {'category':'unit','command':['python','-m','pytest','/acceptance/test_calc.py','-q']},
                {'category':'static','command':['python','-m','mypy','--cache-dir=/tmp/mypy-cache','modern']},
                {'category':'security','command':['python','-m','bandit','-r','modern','-q']}]
            good={'modern/calc.py':'def add(x: int, y: int) -> int:\n    return x + y\n'}
            fixtures=[('correct-calculator',good,args.image,'add'),
                ('wrong-calculator',{'modern/calc.py':'def add(x: int, y: int) -> int:\n    return x - y\n'},args.image,'add'),
                ('tool-shadowing',dict(good,**{'pytest.py':'print("not a test")\n'}),args.image,'add'),
                ('unsupported-scenario',good,args.image,'test_user_cannot_view_approvals_returns_403'),
                ('historical-echo-image',good,args.old_image,'test_user_cannot_view_approvals_returns_403'),
                ('production-security-preflight',good,args.image,'add')]
            provider=None
            if args.provider_evidence:
                provider=json.loads(args.provider_evidence.read_text())
                if provider['status']!='PASS' or provider['ledger']['status']!='COMPLETED':raise ValueError('Actual completed provider evidence is required')
                fixtures.append(('real-provider-generated',provider['changeset']['files'],args.image,'add'))
            first_request=None
            for label,files,image,scenario in fixtures:
                binding={'request_id':uuid.uuid4().hex,'job_id':uuid.uuid4().hex,'attempt_id':uuid.uuid4().hex,
                    'candidate_hash':digest(files),'suite_hash':digest({'scenario':scenario,'x':1,'y':2})}
                body={**binding,'execution':{'purpose':'VERIFICATION' if label=='production-security-preflight' else 'CONTAINMENT_DIAGNOSTIC','image':image,'runtime':'docker-rootless','timeout':35,'files':files,
                    'checks':specs,'adapter':['python','/adapter.py'],
                    'cases':[{'test_case_id':'case-one','name':scenario,'fixtures':{'x':1,'y':2}}]}}
                rpc({**body,'action':'execute'})
                deadline=time.time()+120
                while time.time()<deadline:
                    status=rpc({**binding,'action':'status'})
                    if status['status'] in {'SUCCEEDED','BLOCKED','CANCELLED'}:break
                    time.sleep(0.2)
                result=unseal(status['result'],attestation,expiring=False) if status.get('result') else {}
                raw=result.get('execution',{});observed=raw.get('observation',{});checks=observed.get('checks',[])
                if label in {'correct-calculator','real-provider-generated'}:
                    outcome=raw.get('exit_code')==0 and len(checks)==4 and all(c['status']=='PASS' for c in checks) and all(c.get('case_count',0)>0 for c in checks if c['category']=='unit') and json.loads(observed['observations'][0]['stdout'])['output']==3
                elif label=='wrong-calculator':outcome=any(c['category']=='unit' and c['status']=='FAIL' and c['exit_code']!=0 for c in checks)
                elif label=='tool-shadowing':outcome=raw.get('exit_code') not in {0,None} and 'trusted verification tool' in raw.get('stderr','')
                elif label=='unsupported-scenario':outcome=bool(observed.get('observations')) and observed['observations'][0]['exit_code']==78
                elif label=='historical-echo-image':outcome=status['status']=='BLOCKED' and 'operator-reviewed' in result.get('reason','')
                else:outcome=status['status']=='BLOCKED' and 'execution' not in result
                cleaned=all(result[stage].get('cleanup',{}).get('container_absent') is True for stage in ('preflight','execution','review') if result.get(stage))
                report={'fixture':label,'status':status['status'],'acceptance_result':'PASS' if outcome and cleaned else 'FAIL','result':result}
                reports.append(report)
                print(json.dumps({'fixture':label,'status':status['status'],'reason':result.get('reason'),
                    'checks':[(c['category'],c['status'],c['exit_code']) for c in result.get('execution',{}).get('observation',{}).get('checks',[])]}),flush=True)
                if first_request is None:first_request=(body,binding,status)
            body,binding,original=first_request
            denied=False
            try:rpc({**body,'action':'execute','execution':{**body['execution'],'files':{'escape.py':'changed'}}})
            except urllib.error.HTTPError as exc:denied=exc.code==400
            cross_denied=False
            try:rpc({**binding,'action':'status','job_id':uuid.uuid4().hex})
            except urllib.error.HTTPError as exc:cross_denied=exc.code==400
            server.terminate();server.wait(timeout=15);server=start()
            deadline=time.time()+15
            while True:
                try:recovered=rpc({**binding,'action':'status'});break
                except Exception:
                    if time.time()>deadline:raise
                    time.sleep(0.2)
            evidence={'scope':'Real controller security regression probes; full W09 acceptance remains separate',
                'health':health,'runs':reports,'immutable_input_change_denied':denied,'cross_job_status_denied':cross_denied,
                'persistent_result_survived_restart':recovered==original}
            evidence['counts']={s:sum(r['acceptance_result']==s for r in reports) for s in ('PASS','FAIL')}
            if provider:evidence['provider_lineage']={'local_request_id':provider['request_id'],'provider_request_id':provider['provider_request_id'],
                'changeset_sha256':provider['changeset_sha256'],'evidence_sha256':hashlib.sha256(args.provider_evidence.read_bytes()).hexdigest()}
            with args.output.open('x') as output:json.dump(evidence,output,indent=2)
            print(json.dumps({'evidence':str(args.output),'immutable_input_change_denied':denied,
                'cross_job_status_denied':cross_denied,'persistent_result_survived_restart':recovered==original}),flush=True)
            if evidence['counts']['FAIL'] or not all((denied,cross_denied,recovered==original)):raise SystemExit(1)
        finally:
            if server and server.poll() is None:server.terminate();server.wait(timeout=15)
            log.close()


if __name__=='__main__':main()
