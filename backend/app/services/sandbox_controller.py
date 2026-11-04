"""Standalone Linux sandbox controller. No app config, DB, cloud or artifact credentials.

Run this module as a file with Linux Python. Only this service controls Docker.
Its persistent SQLite queue is local execution state, never the control-plane DB.
"""

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import multiprocessing
from contextlib import nullcontext, contextmanager
import os
from pathlib import Path
import shutil
import sqlite3
import selectors
import signal
import stat
import subprocess
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_harness import HARNESS, HARNESS_VERSION
from sandbox_protocol import canonical, digest, seal, unseal, validate_execution
from sandbox_reviewer import REVIEWER

INSPECTOR = r'''
import hashlib,json,os,pathlib,sys
p=json.load(sys.stdin)
status={k:v.strip() for k,v in (s.split(':',1) for s in pathlib.Path('/proc/self/status').read_text().splitlines() if s.split(':',1)[0] in {'CapEff','NoNewPrivs','Seccomp'})}
limits={}
for name in ('memory.max','pids.max','cpu.max','io.max'):
    f=pathlib.Path('/sys/fs/cgroup')/name
    limits[name]=f.read_text().strip() if f.is_file() else None
adapter=pathlib.Path(p['adapter'])
credentials=sorted(k for k,v in os.environ.items() if v and (k in {'DATABASE_URL','SANDBOX_DISPATCH_KEY','SANDBOX_ATTESTATION_KEY','GOOGLE_APPLICATION_CREDENTIALS'} or k.startswith(('OPENAI_','OPENROUTER_','AWS_','AZURE_'))))
sockets=[name for name in ('/var/run/docker.sock','/run/docker.sock','/run/user/1000/docker.sock') if pathlib.Path(name).exists()]
print(json.dumps({'uid':os.getuid(),'gid':os.getgid(),'uid_map':pathlib.Path('/proc/self/uid_map').read_text().strip(),
    'credential_environment_names':credentials,'docker_socket_paths_present':sockets,'process_security':status,'cgroup_limits':limits,'adapter_sha256':hashlib.sha256(adapter.read_bytes()).hexdigest()}))
'''


def docker(*args, input=None, timeout=15):
    command=['docker',*args]
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    def send():
        try:
            if input: process.stdin.write(input.encode())
            process.stdin.close()
        except (BrokenPipeError,ValueError,OSError): pass
    writer=threading.Thread(target=send,daemon=True);writer.start()
    streams=selectors.DefaultSelector();streams.register(process.stdout,selectors.EVENT_READ,0);streams.register(process.stderr,selectors.EVENT_READ,1)
    output=[bytearray(),bytearray()];deadline=time.monotonic()+timeout
    try:
        while streams.get_map():
            if time.monotonic()>deadline: raise TimeoutError('Docker execution deadline exceeded')
            for key,_ in streams.select(0.1):
                chunk=os.read(key.fileobj.fileno(),65536)
                if not chunk: streams.unregister(key.fileobj);continue
                output[key.data].extend(chunk)
                if sum(map(len,output))>2*1048576: raise ValueError('Docker output exceeded bounded evidence limit')
        process.wait(timeout=5)
        return subprocess.CompletedProcess(command,process.returncode,*(bytes(value).decode('utf-8',errors='replace') for value in output))
    finally:
        streams.close()
        if process.poll() is None: process.kill()
        process.wait(timeout=5)
        process.stdout.close();process.stderr.close()
        writer.join(timeout=1)


def runtime_evidence(runtime):
    proc = docker('info', '--format', '{{json .}}')
    if proc.returncode: raise ValueError('Docker daemon unavailable')
    info = json.loads(proc.stdout)
    security = info.get('SecurityOptions') or []
    if 'name=rootless' not in security or not any(s.startswith('name=seccomp,') for s in security):
        raise ValueError('Actual rootless daemon with seccomp is required')
    selected = 'runsc' if runtime == 'gvisor-rootless' else 'runc'
    if selected not in (info.get('Runtimes') or {}): raise ValueError('Selected runtime unavailable')
    return dict(runtime_name=runtime, selected_runtime=selected, docker_version=info['ServerVersion'],
        security_options=security, cgroup_version=info.get('CgroupVersion'), timestamp=time.time())


@contextmanager
def connect(state):
    db = sqlite3.connect(state, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        with db:yield db
    finally:
        # sqlite3.Connection's context manager commits/rolls back but does not
        # close the handle. Every queue poll and heartbeat must close it.
        db.close()


def initialize(state):
    Path(state).parent.mkdir(parents=True, exist_ok=True)
    with connect(state) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS executions (request_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, attempt_id TEXT NOT NULL, input_hash TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, worker_id TEXT, lease_token TEXT, lease_generation INTEGER NOT NULL DEFAULT 0, lease_expires REAL, started REAL, finished REAL, result TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS controller_meta (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS cleanup_events (container_name TEXT NOT NULL, request_id TEXT NOT NULL, reason TEXT NOT NULL, timestamp REAL NOT NULL)')
        db.execute('INSERT OR IGNORE INTO controller_meta(name,value) VALUES(?,?)',('identity',uuid.uuid4().hex))
    os.chmod(state, 0o600)


def controller_identity(state):
    with connect(state) as db: return db.execute('SELECT value FROM controller_meta WHERE name=?',('identity',)).fetchone()['value']


def inspected_configuration(info, runtime, image):
    h = info['HostConfig']
    if info['Image'] != image or h.get('Runtime') != runtime or info['Config'].get('User') != '65534:65534':
        raise ValueError('Container identity/runtime/UID differ from policy')
    if not h.get('ReadonlyRootfs') or h.get('NetworkMode') != 'none' or h.get('Privileged') or h.get('Binds'):
        raise ValueError('Container filesystem/network/privilege policy violated')
    if h.get('Memory') != 268435456 or h.get('NanoCpus') != 1000000000 or h.get('PidsLimit') != 64 or h.get('CapDrop') != ['ALL']:
        raise ValueError('Container resource/capability policy violated')
    if 'no-new-privileges' not in h.get('SecurityOpt', []): raise ValueError('No-new-privileges missing')
    device=os.environ.get('SANDBOX_IO_DEVICE')
    if device:
        for key,limit_key in (('BlkioDeviceReadBps','SANDBOX_IO_READ_BPS'),('BlkioDeviceWriteBps','SANDBOX_IO_WRITE_BPS')):
            if not any(item.get('Path')==device and item.get('Rate')==int(os.environ[limit_key]) for item in h.get(key,[])):
                raise ValueError('Actual container block I/O configuration differs from policy')
    if any(m.get('Type')!='tmpfs' or m.get('Destination') not in {'/work','/tmp'} for m in info.get('Mounts',[])):
        raise ValueError('Image introduced an unapproved writable volume')
    return {k: h.get(k) for k in ('Runtime','NetworkMode','ReadonlyRootfs','Memory','NanoCpus','PidsLimit','CapDrop','SecurityOpt','Tmpfs','Binds','BlkioDeviceReadBps','BlkioDeviceWriteBps')}


def io_policy_enforced(limits):
    device=os.environ.get('SANDBOX_IO_DEVICE')
    if not device:return False
    identity=os.stat(device).st_rdev
    expected=f'{os.major(identity)}:{os.minor(identity)}'
    for line in (limits.get('io.max') or '').splitlines():
        parts=line.split()
        if not parts or parts[0]!=expected:continue
        values=dict(part.split('=',1) for part in parts[1:])
        return values.get('rbps')==os.environ.get('SANDBOX_IO_READ_BPS') and values.get('wbps')==os.environ.get('SANDBOX_IO_WRITE_BPS')
    return False


def execute_container(request, program, data, stage):
    body=request['execution']; image=body['image']; deadline=time.time()+body['timeout']
    runtime=runtime_evidence(body['runtime']); name='rebase-'+request['request_id'][:80]+'-'+stage
    result={'stage':stage,'worker_id':name,'started_at':time.time(),'deadline_at':deadline,'runtime_evidence':runtime}
    try:
        io_flags=[]
        device=os.environ.get('SANDBOX_IO_DEVICE','')
        if device:
            if not device.startswith('/dev/') or not stat.S_ISBLK(os.stat(device).st_mode):
                raise ValueError('I/O policy must identify an actual operator-approved block device')
            for option,key in (('--device-read-bps','SANDBOX_IO_READ_BPS'),('--device-write-bps','SANDBOX_IO_WRITE_BPS')):
                limit=int(os.environ.get(key,'0'))
                if not 1048576<=limit<=1073741824:raise ValueError('Invalid bounded I/O policy')
                io_flags.append(option+'='+device+':'+str(limit))
        # Serialize creation with cancellation. A cancelled task cannot create
        # another container after its cancellation cleanup has completed.
        with connect(request['_state']) if request.get('_state') else nullcontext() as db:
            if db:
                db.execute('BEGIN IMMEDIATE')
                active=db.execute('SELECT status,lease_token,lease_expires FROM executions WHERE request_id=?',(request['request_id'],)).fetchone()
                if not active or active['status']!='RUNNING' or active['lease_token']!=request['_lease_token'] or active['lease_expires']<time.time():
                    raise ValueError('Cancelled or stale execution cannot create a container')
            created=docker('create',*io_flags,'--name',name,'--interactive','--pull=never',
            '--label','rebase.controller='+request['_controller_id'],'--label','rebase.request='+request['request_id'],
            '--label','rebase.job='+request['job_id'],'--label','rebase.attempt='+request['attempt_id'],
            '--label','rebase.deadline='+str(deadline), '--runtime='+runtime['selected_runtime'],
            '--network=none','--read-only','--memory=256m','--cpus=1','--pids-limit=64',
            '--cap-drop=ALL','--security-opt=apparmor=docker-default','--security-opt=no-new-privileges',
            '--user=65534:65534','--log-driver=none',
            '--tmpfs=/work:rw,noexec,nosuid,nodev,size=128m,mode=1777','--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=32m',
            '--entrypoint','/usr/local/bin/python',image,'-I','-c',program)
        if created.returncode: raise ValueError('Container creation failed: '+created.stderr[:500])
        inspected=docker('inspect',name)
        if inspected.returncode: raise ValueError('Container inspect failed')
        info=json.loads(inspected.stdout)[0]
        result.update(container_id=info['Id'],image_digest=info['Image'],execution_uid=info['Config']['User'],
            container_configuration=inspected_configuration(info,runtime['selected_runtime'],image))
        run=docker('start','--attach','--interactive',name,input=canonical(data).decode(),timeout=body['timeout'])
        result.update(exit_code=run.returncode,stdout=run.stdout[:1048576],stderr=run.stderr[:32768],
            logs_hash=hashlib.sha256((run.stdout+'\n'+run.stderr).encode()).hexdigest())
        if run.returncode==0: result['observation']=json.loads(run.stdout)
    except Exception as exc:
        result.update(exit_code=None,error=type(exc).__name__+': '+str(exc)[:700])
    finally:
        removed=docker('rm','--force',name)
        absent=docker('inspect',name)
        result['cleanup']={'remove_exit_code':removed.returncode,'container_absent':absent.returncode!=0}
        if request.get('_state'):
            with connect(request['_state']) as db:
                event=db.execute('SELECT reason,timestamp FROM cleanup_events WHERE container_name=? ORDER BY timestamp DESC LIMIT 1',(name,)).fetchone()
            if event: result['termination']={'reason':event['reason'],'timestamp':event['timestamp']}
        result['finished_at']=time.time()
    return result


def scan_image(image):
    tool=shutil.which('trivy')
    if not tool: return {'status':'NOT_RUN','reason':'Operator image vulnerability scanner trivy is unavailable','image_digest':image}
    try:
        version=subprocess.run([tool,'--version'],capture_output=True,text=True,timeout=5)
        scan=subprocess.run([tool,'image','--skip-db-update','--skip-java-db-update','--offline-scan','--scanners','vuln','--image-src','docker','--format','json',image],capture_output=True,text=True,timeout=45)
        if scan.returncode: return {'status':'BLOCKED','reason':'Offline image vulnerability scan unavailable','image_digest':image,'tool':'trivy','tool_version':version.stdout[:500]}
        report=json.loads(scan.stdout)
        critical=[v for r in report.get('Results',[]) for v in r.get('Vulnerabilities',[]) if v.get('Severity') in {'HIGH','CRITICAL'}]
        return {'status':'FAIL' if critical else 'PASS','tool':'trivy','tool_version':version.stdout[:500],
            'image_digest':image,'report_hash':hashlib.sha256(scan.stdout.encode()).hexdigest(),'blocking_findings':critical}
    except Exception as exc: return {'status':'BLOCKED','reason':type(exc).__name__,'image_digest':image}


def worker_loop(state,attestation_key,stop):
    worker_id='verifier-'+str(os.getpid())+'-'+uuid.uuid4().hex
    while not stop.is_set():
        with connect(state) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT * FROM executions WHERE status='QUEUED' ORDER BY rowid LIMIT 1").fetchone()
            if row:
                token=uuid.uuid4().hex
                db.execute("UPDATE executions SET status='RUNNING',worker_id=?,lease_token=?,lease_generation=lease_generation+1,lease_expires=?,started=? WHERE request_id=? AND status='QUEUED'",(worker_id,token,time.time()+40,time.time(),row['request_id']))
        if not row: stop.wait(0.5);continue
        request=json.loads(row['payload']);request['_controller_id']=controller_identity(state)
        request['_state']=state;request['_lease_token']=token
        request_id=row['request_id'];heartbeat_stop=threading.Event();preflight=None;scan=None
        def heartbeat():
            while not heartbeat_stop.wait(5):
                with connect(state) as db:
                    db.execute("UPDATE executions SET lease_expires=? WHERE request_id=? AND lease_token=? AND status='RUNNING'",(time.time()+40,request_id,token))
        heartbeat_thread=threading.Thread(target=heartbeat,daemon=True);heartbeat_thread.start()
        try:
            if request['expires_at']<time.time(): raise ValueError('Execution capability expired before dispatch')
            body=request['execution']
            diagnostic=body.get('purpose')=='CONTAINMENT_DIAGNOSTIC'
            if diagnostic and os.environ.get('SANDBOX_ALLOW_DIAGNOSTICS')!='1':
                raise ValueError('Containment diagnostics are disabled on this verification controller')
            scan=scan_image(body['image'])
            if scan['status']!='PASS' and not diagnostic:
                raise ValueError('Image security is '+scan['status']+': '+scan.get('reason','blocking findings'))
            preflight=execute_container(request,INSPECTOR,{'adapter':body['adapter'][1]},'preflight')
            security=preflight.get('observation') or {}
            approved_hashes=set(json.loads(os.environ.get('SANDBOX_ALLOWED_ADAPTER_HASHES','[]')))
            if preflight.get('exit_code')!=0 or security.get('adapter_sha256') not in approved_hashes:
                raise ValueError('Image adapter is not an operator-reviewed application observer')
            if security.get('uid')!=65534 or security.get('process_security')!={'CapEff':'0000000000000000','NoNewPrivs':'1','Seccomp':'2'}:
                raise ValueError('Actual execution privileges differ from security policy')
            if security.get('credential_environment_names') or security.get('docker_socket_paths_present'):
                raise ValueError('Build worker has forbidden credentials or Docker socket access')
            limits=security['cgroup_limits']
            if limits.get('memory.max')!='268435456' or limits.get('pids.max')!='64':
                raise ValueError('Kernel memory/PID limits are not enforced')
            cpu=(limits.get('cpu.max') or '').split()
            if len(cpu)!=2 or cpu[0]=='max' or int(cpu[0])>int(cpu[1]): raise ValueError('Kernel CPU limit is not enforced')
            if not diagnostic and not io_policy_enforced(limits):
                raise ValueError('Required kernel I/O limits are not enforced; deployment policy is required')
            execution=execute_container(request,HARNESS,body,'verify')
            with connect(state) as db:
                active=db.execute('SELECT status FROM executions WHERE request_id=?',(request_id,)).fetchone()
                if not active or active['status']!='RUNNING': raise ValueError('Execution was cancelled or its lease expired')
            review=execute_container(request,REVIEWER,{'files':body['files']},'review')
            result={k:request[k] for k in ('request_id','job_id','attempt_id','candidate_hash','suite_hash')}
            with connect(state) as db:
                current=db.execute('SELECT lease_expires,status FROM executions WHERE request_id=? AND lease_token=?',(request_id,token)).fetchone()
                if not current or current['status']!='RUNNING' or current['lease_expires']<time.time():
                    raise ValueError('Stale worker completion fenced')
            result.update(input_hash=row['input_hash'],worker_id=worker_id,lease_token=token,lease_generation=row['lease_generation']+1,lease_expires_at=current['lease_expires'],
                harness_version=HARNESS_VERSION,execution_purpose=body.get('purpose','VERIFICATION'),preflight=preflight,execution=execution,review=review,image_scan=scan)
            signed=seal(result,attestation_key)
            with connect(state) as db:
                db.execute("UPDATE executions SET status='SUCCEEDED',finished=?,result=? WHERE request_id=? AND lease_token=? AND status='RUNNING' AND lease_expires>?",(time.time(),canonical(signed).decode(),request_id,token,time.time()))
        except Exception as exc:
            failure=seal({'request_id':request_id,'job_id':request['job_id'],'attempt_id':request['attempt_id'],
                'reason':type(exc).__name__+': '+str(exc)[:700],'preflight':preflight,'image_scan':scan},attestation_key)
            with connect(state) as db: db.execute("UPDATE executions SET status='BLOCKED',finished=?,result=? WHERE request_id=? AND lease_token=? AND status='RUNNING'",(time.time(),canonical(failure).decode(),request_id,token))
        finally:
            heartbeat_stop.set();heartbeat_thread.join(timeout=2)


def garbage_collect(state):
    listed=docker('ps','--all','--filter','label=rebase.controller='+controller_identity(state),'--format','{{.ID}}')
    for identity in listed.stdout.split():
        info=docker('inspect',identity)
        if info.returncode: continue
        labels=json.loads(info.stdout)[0]['Config'].get('Labels') or {}
        with connect(state) as db:
            task=db.execute('SELECT status,lease_expires FROM executions WHERE request_id=?',(labels.get('rebase.request'),)).fetchone()
        expired=float(labels.get('rebase.deadline','0'))<time.time()
        if expired or not task or task['status']!='RUNNING' or (task['lease_expires'] or 0)<time.time():
            reason='DEADLINE_EXCEEDED' if expired else 'CANCELLED' if task and task['status']=='CANCELLED' else 'ORPHANED_OR_EXPIRED_LEASE'
            name=json.loads(info.stdout)[0]['Name'].lstrip('/')
            with connect(state) as db:
                db.execute('INSERT INTO cleanup_events VALUES(?,?,?,?)',(name,labels.get('rebase.request',''),reason,time.time()))
            docker('rm','--force',identity)
    with connect(state) as db:
        db.execute("UPDATE executions SET status='BLOCKED',finished=? WHERE status='RUNNING' AND lease_expires<?",(time.time(),time.time()))


def serve(address,state,images,dispatch_key,attestation_key):
    initialize(state);stop=multiprocessing.Event()
    worker=multiprocessing.Process(target=worker_loop,args=(state,attestation_key,stop),daemon=True);worker.start()
    def reap():
        nonlocal worker
        while not stop.wait(5):
            try:
                if not worker.is_alive():
                    previous_pid=worker.pid;worker.join(timeout=1)
                    with connect(state) as db:
                        orphaned=db.execute("SELECT request_id,job_id,attempt_id FROM executions WHERE status='RUNNING' AND worker_id LIKE ?",('verifier-'+str(previous_pid)+'-%',)).fetchall()
                        for task in orphaned:
                            failure=seal({**dict(task),'reason':'Independent worker crashed; its lease was revoked and containers reclaimed','failure_classification':'WORKER_CRASH'},attestation_key)
                            db.execute("UPDATE executions SET status='BLOCKED',finished=?,result=? WHERE request_id=? AND status='RUNNING'",(time.time(),canonical(failure).decode(),task['request_id']))
                    garbage_collect(state)
                    if stop.is_set():return
                    worker=multiprocessing.Process(target=worker_loop,args=(state,attestation_key,stop),daemon=True);worker.start()
                    print(json.dumps({'event':'VERIFIER_WORKER_REPLACED','previous_pid':previous_pid,'worker_pid':worker.pid}),file=sys.stderr,flush=True)
                else:garbage_collect(state)
            except Exception as exc:
                print(json.dumps({'event':'CONTROLLER_REAPER_ERROR','error_type':type(exc).__name__}),file=sys.stderr,flush=True)
    threading.Thread(target=reap,daemon=True).start()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=17*1024*1024: raise ValueError('Request too large')
                request=unseal(json.loads(self.rfile.read(length)),dispatch_key)
                action=request.get('action')
                if action=='health':
                    present=[];blocked=[]
                    for image in sorted(images):
                        found=docker('image','inspect',image,'--format','{{.Id}}')
                        if found.returncode==0 and found.stdout.strip()==image: present.append(image)
                        else: blocked.append('Approved image unavailable: '+image)
                    if not shutil.which('trivy'): blocked.append('Image vulnerability scanner trivy is unavailable')
                    if not os.environ.get('SANDBOX_IO_DEVICE'): blocked.append('Mandatory block I/O policy is not configured')
                    if not worker.is_alive(): blocked.append('Independent worker is unavailable')
                    answer={'status':'blocked' if blocked else 'ready','runtime':runtime_evidence(request.get('runtime','docker-rootless')),
                        'worker_alive':worker.is_alive(),'worker_pid':worker.pid,'images':present,'blocked_reasons':blocked}
                else:
                    for key in ('request_id','job_id','attempt_id'):
                        if not request.get(key): raise ValueError('Missing scope')
                    with connect(state) as db:
                        row=db.execute('SELECT * FROM executions WHERE request_id=?',(request['request_id'],)).fetchone()
                        if row and (row['job_id']!=request['job_id'] or row['attempt_id']!=request['attempt_id']): raise ValueError('Cross-attempt request denied')
                        if action=='execute':
                            validate_execution(request,images)
                            identity=digest({k:v for k,v in request.items() if k not in {'expires_at','action','nonce'}})
                            if row and row['input_hash']!=identity: raise ValueError('Request ID already belongs to different immutable inputs')
                            if not row:
                                db.execute('INSERT INTO executions(request_id,job_id,attempt_id,input_hash,payload,status) VALUES(?,?,?,?,?,?)',(request['request_id'],request['job_id'],request['attempt_id'],identity,canonical(request).decode(),'QUEUED'))
                            answer={'status':row['status'] if row else 'QUEUED','request_id':request['request_id']}
                        elif action=='status':
                            if not row: raise ValueError('Unknown execution')
                            answer={'status':row['status'],'result':json.loads(row['result']) if row['result'] else None}
                        elif action=='cancel':
                            if row and row['status'] in {'QUEUED','RUNNING'}:
                                db.execute("UPDATE executions SET status='CANCELLED',finished=? WHERE request_id=?",(time.time(),request['request_id']))
                                for stage in ('preflight','verify','review'): docker('rm','--force','rebase-'+request['request_id'][:80]+'-'+stage)
                            answer={'status':'CANCELLED'}
                        else: raise ValueError('Unknown action')
                answer['rpc_nonce']=request.get('nonce')
                raw=canonical(seal(answer,attestation_key));self.send_response(200)
            except Exception as exc:
                raw=canonical({'error':type(exc).__name__,'reason':str(exc)[:500]});self.send_response(400)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(address,Handler)
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM,lambda *args:threading.Thread(target=server.shutdown,daemon=True).start())
    try: server.serve_forever()
    finally:
        stop.set();worker.join(timeout=5)
        if worker.is_alive(): worker.terminate();worker.join(timeout=3)
        with connect(state) as db: db.execute("UPDATE executions SET status='BLOCKED',finished=? WHERE status='RUNNING'",(time.time(),))
        garbage_collect(state);server.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8093);parser.add_argument('--state',required=True);args=parser.parse_args()
    if any(os.environ.get(k) for k in ('DATABASE_URL','OPENAI_API_KEY','AWS_SECRET_ACCESS_KEY','AZURE_CLIENT_SECRET')):
        raise SystemExit('Controller must run without control-plane/cloud/provider credentials')
    images=set(json.loads(os.environ.get('SANDBOX_ALLOWED_IMAGES','[]')))
    if not images: raise SystemExit('Operator-approved immutable image allowlist is required')
    if not json.loads(os.environ.get('SANDBOX_ALLOWED_ADAPTER_HASHES','[]')):
        raise SystemExit('Operator-reviewed immutable adapter SHA-256 allowlist is required')
    serve((args.host,args.port),args.state,images,os.environ['SANDBOX_DISPATCH_KEY'],os.environ['SANDBOX_ATTESTATION_KEY'])
