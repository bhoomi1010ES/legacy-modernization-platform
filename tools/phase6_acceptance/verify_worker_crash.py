"""Real worker-crash lease expiry and orphan cleanup, with no mocked Docker calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[2];SERVICES=ROOT/'backend/app/services'
sys.path.insert(0,str(SERVICES))
from sandbox_protocol import canonical,digest,seal,unseal


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--image',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise ValueError('Evidence must not be overwritten')
    dispatch=secrets.token_hex(32);attestation=secrets.token_hex(32)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    def rpc(body):
        nonce=uuid.uuid4().hex
        request=urllib.request.Request(f'http://127.0.0.1:{port}/v1/rpc',method='POST',headers={'Content-Type':'application/json'},
            data=canonical(seal({**body,'nonce':nonce,'expires_at':time.time()+120},dispatch)))
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=15) as response:
            answer=unseal(json.load(response),attestation,expiring=False)
            if answer.pop('rpc_nonce')!=nonce:raise ValueError('RPC replay')
            return answer
    with tempfile.TemporaryDirectory(prefix='rebase-w09-crash-test-') as folder:
        root=Path(folder);state=root/'execution_test.sqlite'
        env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','XDG_RUNTIME_DIR','LANG','LC_ALL',
            'SANDBOX_IO_DEVICE','SANDBOX_IO_READ_BPS','SANDBOX_IO_WRITE_BPS'}}
        env.update(DOCKER_CONTEXT='rootless',SANDBOX_ALLOW_DIAGNOSTICS='1',SANDBOX_DISPATCH_KEY=dispatch,SANDBOX_ATTESTATION_KEY=attestation,
            SANDBOX_ALLOWED_IMAGES=json.dumps([args.image]),SANDBOX_ALLOWED_ADAPTER_HASHES=json.dumps([hashlib.sha256((ROOT/'tools/phase6_acceptance/image/adapter.py').read_bytes()).hexdigest()]))
        def start(log):return subprocess.Popen([sys.executable,str(SERVICES/'sandbox_controller.py'),'--port',str(port),'--state',str(state)],env=env,stdout=log,stderr=log)
        def inspect(name):return subprocess.run(['docker','--context=rootless','inspect',name],capture_output=True,text=True,timeout=8,env=env)
        with (root/'controller.log').open('w+') as log:
            server=start(log)
            try:
                deadline=time.time()+20
                while True:
                    try:initial=rpc({'action':'health'});break
                    except Exception:
                        if time.time()>deadline:raise
                        time.sleep(.2)
                files={'modern/calc.py':'def add(x,y):\n    import time\n    while True: time.sleep(.1)\n'}
                binding={k:uuid.uuid4().hex for k in ('request_id','job_id','attempt_id')}
                binding.update(candidate_hash=digest(files),suite_hash=digest({'crash-probe-v1':True}))
                body={**binding,'execution':{'purpose':'CONTAINMENT_DIAGNOSTIC','image':args.image,'runtime':'docker-rootless','timeout':120,'files':files,'checks':[],
                    'adapter':['python','/adapter.py'],'cases':[{'test_case_id':'crash','name':'add','fixtures':{'x':1,'y':2}}]}}
                rpc({**body,'action':'execute'});name='rebase-'+binding['request_id']+'-verify'
                deadline=time.time()+25
                while True:
                    container=inspect(name)
                    if container.returncode==0 and json.loads(container.stdout)[0]['State']['Running']:break
                    if time.time()>deadline:raise RuntimeError('Verification container never started')
                    time.sleep(.2)
                actual=json.loads(container.stdout)[0]
                with sqlite3.connect(state) as db:
                    worker_id=db.execute('SELECT worker_id FROM executions WHERE request_id=?',(binding['request_id'],)).fetchone()[0]
                worker_pid=int(worker_id.split('-')[1])
                # Python may use a forkserver and resource tracker, so the worker
                # is not necessarily the controller's only direct child.
                ancestor=worker_pid
                while ancestor>1 and ancestor!=server.pid:
                    status=Path(f'/proc/{ancestor}/status').read_text()
                    ancestor=int(next(line.split(':',1)[1] for line in status.splitlines() if line.startswith('PPid:')))
                if ancestor!=server.pid:raise RuntimeError('Worker is not a descendant of this isolated test controller')
                os.kill(worker_pid,signal.SIGKILL);killed=time.time()
                print(json.dumps({'stage':'worker_killed','container_was_running':True}),flush=True)
                deadline=time.time()+60
                while True:
                    status=rpc({**binding,'action':'status'})
                    absent=inspect(name).returncode!=0
                    if status['status']=='BLOCKED' and absent:break
                    if time.time()>deadline:raise RuntimeError('Orphan cleanup did not reclaim the expired worker lease')
                    time.sleep(.5)
                health=rpc({'action':'health'})
                server.terminate();server.wait(timeout=20);server=start(log)
                deadline=time.time()+20
                while True:
                    try:recovered=rpc({**binding,'action':'status'});break
                    except Exception:
                        if time.time()>deadline:raise
                        time.sleep(.2)
                replaced=health['worker_alive'] is True and health.get('worker_pid')!=worker_pid
                evidence={'status':'PASS' if recovered['status']=='BLOCKED' and absent and replaced else 'FAIL',
                    'scope':'Actual worker crash; persistent scoped task and lease cleanup. No W09 delivery PASS claim.',
                    'binding':binding,'image_digest':actual['Image'],'runtime':actual['HostConfig']['Runtime'],'uid':actual['Config']['User'],
                    'runtime_health':initial,'failed_task_reported_blocked':status['status']=='BLOCKED','replacement_worker_ready':replaced,
                    'cleanup_confirmed':absent,'seconds_to_reclaim':time.time()-killed,'status_after_restart':recovered['status']}
                args.output.parent.mkdir(parents=True,exist_ok=True)
                with args.output.open('x') as output:json.dump(evidence,output,indent=2)
                print(json.dumps(evidence),flush=True)
                return 0 if evidence['status']=='PASS' else 1
            finally:
                if server.poll() is None:server.terminate();server.wait(timeout=20)


if __name__=='__main__':sys.exit(main())
