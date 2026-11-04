"""Bounded real-container containment probes. Image scanning is reported separately.

Run with Linux Python against the WSL rootless context. No provider/DB keys are
passed to the controller. Policy denials are distinguished from executed probes.
"""
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
    parser=argparse.ArgumentParser()
    parser.add_argument('--image',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): raise ValueError('Existing evidence cannot be overwritten')
    dispatch=secrets.token_hex(32);attestation=secrets.token_hex(32)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    def rpc(body):
        nonce=uuid.uuid4().hex
        request=urllib.request.Request(f'http://127.0.0.1:{port}/v1/rpc',
            data=canonical(seal({**body,'nonce':nonce,'expires_at':time.time()+120},dispatch)),
            headers={'Content-Type':'application/json'},method='POST')
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=20) as response:
            result=unseal(json.load(response),attestation,expiring=False)
            if result.pop('rpc_nonce')!=nonce: raise ValueError('RPC response replay')
            return result
    reports=[]
    with tempfile.TemporaryDirectory(prefix='rebase-w09-hostile-test-') as folder:
        parent=Path(folder)
        secret=parent/'host-only-secret.txt';secret.write_text('non-sensitive-containment-canary')
        tenant=parent/'other-tenant.txt';tenant.write_text('other-tenant-canary')
        state=parent/'execution_test.sqlite'
        environment={k:v for k,v in os.environ.items() if k in {'PATH','HOME','XDG_RUNTIME_DIR','LANG','LC_ALL',
            'SANDBOX_IO_DEVICE','SANDBOX_IO_READ_BPS','SANDBOX_IO_WRITE_BPS'}}
        environment.update(DOCKER_CONTEXT='rootless',SANDBOX_ALLOW_DIAGNOSTICS='1',SANDBOX_DISPATCH_KEY=dispatch,SANDBOX_ATTESTATION_KEY=attestation,
            SANDBOX_ALLOWED_IMAGES=json.dumps([args.image]),
            SANDBOX_ALLOWED_ADAPTER_HASHES=json.dumps([hashlib.sha256((ROOT/'tools/phase6_acceptance/image/adapter.py').read_bytes()).hexdigest()]))
        with (parent/'controller.log').open('w+') as log:
            server=subprocess.Popen([sys.executable,str(SERVICES/'sandbox_controller.py'),'--port',str(port),'--state',str(state)],
                env=environment,stdout=log,stderr=log)
            try:
                deadline=time.time()+20
                while True:
                    try: health=rpc({'action':'health','runtime':'docker-rootless'});break
                    except Exception:
                        if time.time()>deadline: raise RuntimeError('Controller startup failed')
                        time.sleep(.2)
                def code(body):
                    return 'def add(x, y):\n'+''.join('    '+line+'\n' for line in body.strip().splitlines())
                def request(files,timeout=12,checks=None):
                    return dict(request_id=uuid.uuid4().hex,job_id=uuid.uuid4().hex,attempt_id=uuid.uuid4().hex,
                        candidate_hash=digest(files),suite_hash=digest({'containment-v1':True}),
                        execution=dict(purpose='CONTAINMENT_DIAGNOSTIC',image=args.image,runtime='docker-rootless',timeout=timeout,files=files,
                            checks=checks or [],adapter=['python','/adapter.py'],
                            cases=[dict(test_case_id='containment-probe',name='add',fixtures={'x':1,'y':2})]))
                def finish(body):
                    deadline=time.time()+90
                    while time.time()<deadline:
                        status=rpc({**body,'action':'status'})
                        if status['status'] in {'SUCCEEDED','BLOCKED','CANCELLED'}:
                            return status,unseal(status['result'],attestation,expiring=False) if status.get('result') else {}
                        time.sleep(.15)
                    raise TimeoutError('Controller task did not finish')
                def absent(body):
                    result=subprocess.run(['docker','--context=rootless','ps','-aq','--filter','label=rebase.request='+body['request_id']],
                        capture_output=True,text=True,timeout=10,env=environment)
                    return result.returncode==0 and not result.stdout.strip()
                denied_read=lambda path:code(f"from pathlib import Path\nreturn not Path({str(path)!r}).exists()")
                fixtures=[
                    ('path-traversal',{'../../escape.py':'unsafe'},'POLICY_DENIAL'),
                    ('symlink-escape',{'modern/calc.py':code(f"import os\nfrom pathlib import Path\nos.symlink({str(secret)!r}, '/work/link')\nreturn not Path('/work/link').exists()")},'TRUE'),
                    ('host-secret-access',{'modern/calc.py':denied_read(secret)},'TRUE'),
                    ('docker-socket-access',{'modern/calc.py':code("from pathlib import Path\nreturn not any(Path(p).exists() for p in ('/var/run/docker.sock','/run/user/1000/docker.sock'))")},'TRUE'),
                    ('cloud-metadata-access',{'modern/calc.py':code("import socket\ns=socket.socket();s.settimeout(1)\ntry:\n    s.connect(('169.254.169.254',80))\n    return False\nexcept OSError:\n    return True\nfinally:\n    s.close()")},'TRUE'),
                    ('other-tenant-access',{'modern/calc.py':denied_read(tenant)},'TRUE'),
                    ('fork-bomb-bounded',{'modern/calc.py':code("import subprocess\nchildren=[]\ntry:\n    for i in range(80):\n        try: children.append(subprocess.Popen(['/usr/local/bin/python','-I','-c','import time;time.sleep(8)']))\n        except OSError: return len(children)<80\n    return False\nfinally:\n    for child in children: child.kill()\n    for child in children: child.wait()")},'TRUE'),
                    ('infinite-loop',{'modern/calc.py':code("while True: pass")},'DEADLINE'),
                    ('network-egress',{'modern/calc.py':code("import socket\ns=socket.socket();s.settimeout(1)\ntry:\n    s.connect(('1.1.1.1',443))\n    return False\nexcept OSError:\n    return True\nfinally:\n    s.close()")},'TRUE'),
                    ('unexpected-install',{'modern/calc.py':code('return x+y')},'INSTALL_DENIAL'),
                    ('unsafe-submodule', {'.gitmodules':'[submodule "unsafe"]\nurl = ext::unsafe\n'},'POLICY_DENIAL'),
                    ('unsafe-git-hook', {'.git/hooks/post-checkout':'unsafe'},'POLICY_DENIAL'),
                    ('archive-traversal',{'modern/calc.py':code("import io,zipfile\nfrom pathlib import Path\nb=io.BytesIO()\nwith zipfile.ZipFile(b,'w') as z: z.writestr('../../etc/rebase-probe','canary')\nb.seek(0)\ntry:\n    with zipfile.ZipFile(b) as z:\n        for item in z.infolist():\n            target=Path('/work')/item.filename\n            target.write_bytes(z.read(item))\n    return False\nexcept OSError:\n    return not Path('/etc/rebase-probe').exists()")},'TRUE'),
                    ('archive-bomb-bounded',{'modern/calc.py':code("import io,zipfile\nb=io.BytesIO()\nwith zipfile.ZipFile(b,'w',compression=zipfile.ZIP_DEFLATED) as z:\n    for n in range(12): z.writestr(str(n),b'0'*(4*1024*1024))\nb.seek(0)\ntry:\n    with zipfile.ZipFile(b) as z: z.extractall('/tmp/bomb')\n    return False\nexcept OSError as e:\n    return e.errno==28")},'TRUE'),
                ]
                for label,files,expected in fixtures:
                    body=request(files,timeout=5 if expected=='DEADLINE' else 15,
                        checks=[{'category':'build','command':['npm','install']}] if expected=='INSTALL_DENIAL' else None)
                    started=time.time();result={};denied=False;status={}
                    try:
                        rpc({**body,'action':'execute'});status,result=finish(body)
                    except urllib.error.HTTPError as exc:
                        denied=exc.code==400
                    run=result.get('execution') or {}
                    observed=(run.get('observation') or {}).get('observations') or []
                    output=json.loads(observed[0]['stdout']).get('output') if observed and observed[0].get('exit_code')==0 else None
                    deadline_enforced=('deadline' in run.get('error','').lower() or run.get('termination',{}).get('reason')=='DEADLINE_EXCEEDED')
                    passed=denied if expected.endswith('DENIAL') else output is True if expected=='TRUE' else deadline_enforced
                    cleaned=absent(body)
                    reports.append(dict(fixture=label,attempt_id=body['attempt_id'],request_id=body['request_id'],
                        image_digest=args.image,expected=expected,actual={'policy_denied':denied,'output':output,'status':status.get('status')},
                        execution_mode='POLICY_REJECTION' if denied else 'REAL_SANDBOX',started_at=started,finished_at=time.time(),
                        evidence=result,cleanup_confirmed=cleaned,status='PASS' if passed and cleaned else 'FAIL'))
                    print(json.dumps({'fixture':label,'status':reports[-1]['status'],'expected':expected,'cleanup':cleaned}),flush=True)
                # The parent and three children must disappear on cancellation.
                files={'modern/calc.py':code("import subprocess,time\nchildren=[subprocess.Popen(['/usr/local/bin/python','-I','-c','import time;time.sleep(120)']) for i in range(3)]\nwhile True: time.sleep(.1)")}
                body=request(files,timeout=45);rpc({**body,'action':'execute'})
                deadline=time.time()+25;running=False
                while time.time()<deadline:
                    inspected=subprocess.run(['docker','--context=rootless','inspect','rebase-'+body['request_id']+'-verify'],capture_output=True,text=True,env=environment)
                    if inspected.returncode==0 and json.loads(inspected.stdout)[0]['State']['Running']:
                        # Wait for the child process tree to exist, using docker top.
                        top=subprocess.run(['docker','--context=rootless','top','rebase-'+body['request_id']+'-verify'],capture_output=True,text=True,env=environment)
                        if top.returncode==0 and len(top.stdout.splitlines())>=6: running=True;break
                    time.sleep(.2)
                cancelled=rpc({**body,'action':'cancel'});time.sleep(.5)
                reports.append(dict(fixture='process-tree-cancellation',attempt_id=body['attempt_id'],request_id=body['request_id'],image_digest=args.image,
                    expected='Running child tree removed',actual={'running_tree_observed':running,'reply':cancelled},cleanup_confirmed=absent(body),
                    status='PASS' if running and cancelled['status']=='CANCELLED' and absent(body) else 'FAIL'))
                print(json.dumps({'fixture':reports[-1]['fixture'],'status':reports[-1]['status']}),flush=True)
                assert secret.read_text()=='non-sensitive-containment-canary' and tenant.read_text()=='other-tenant-canary'
                evidence={'scope':'Real bounded containment probes; not full W09 acceptance. Missing tools never count as verification PASS.',
                    'health':health,'fixtures':reports,'counts':{s:sum(r['status']==s for r in reports) for s in ('PASS','FAIL')},
                    'host_canaries_unchanged':True}
                args.output.parent.mkdir(parents=True,exist_ok=True)
                with args.output.open('x') as output: json.dump(evidence,output,indent=2)
                print(json.dumps({'evidence':str(args.output),'counts':evidence['counts']}),flush=True)
                return 1 if evidence['counts']['FAIL'] else 0
            finally:
                server.terminate();server.wait(timeout=20)


if __name__=='__main__':sys.exit(main())
