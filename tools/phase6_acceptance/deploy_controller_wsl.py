"""Deploy the user-approved standalone controller without printing service keys."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend/app/services'))
from sandbox_protocol import canonical,seal,unseal


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise ValueError('Evidence must not be overwritten')
    if not (Path.home()/'.local/bin/trivy').is_file():raise ValueError('Approved Trivy installation is required')
    io=json.loads((ROOT/'docs/audits/W09_IO_LIMITS_20261102.json').read_text())
    if io['status']!='PASS':raise ValueError('Actual kernel I/O enforcement is required')
    device=subprocess.run(['findmnt','-no','SOURCE','-T',str(Path.home()/'.local/share/docker')],capture_output=True,text=True,check=True).stdout.strip()
    if device!=io['block_device'] or not stat.S_ISBLK(os.stat(device).st_mode):raise ValueError('Docker storage block device changed since the approved preflight')
    folder=Path.home()/'.config/rebase';folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=folder/'sandbox-controller.json'
    images=['sha256:afad74cbf6c87d0bd550e5b33496713aaeecafb45f052b9dc8bfc279435970f3','sha256:42372f8e665d07f55d3d62d8c905f3b2f31295c91e439d05eea277d42bd85112']
    if path.exists():
        if path.is_symlink() or path.stat().st_mode & 0o077:raise ValueError('Existing controller configuration is not private')
        config=json.loads(path.read_text())
        backup=path.with_name('sandbox-controller.before-w09-'+str(time.time_ns())+'.json');shutil.copy2(path,backup);backup.chmod(0o600)
    else:config={'SANDBOX_DISPATCH_KEY':secrets.token_hex(32),'SANDBOX_ATTESTATION_KEY':secrets.token_hex(32)}
    config.update(SANDBOX_ALLOWED_IMAGES=images,
        SANDBOX_ALLOWED_ADAPTER_HASHES=['93382cb3be18c97afbf420d15cfe8c68fba8b9124f6bfd6c6278ce468f5bc75d'],
        SANDBOX_IO_DEVICE=device,SANDBOX_IO_READ_BPS=10485760,SANDBOX_IO_WRITE_BPS=10485760)
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(descriptor,'w') as output:json.dump(config,output,indent=2)
    path.chmod(0o600)
    unit=Path.home()/'.config/systemd/user/rebase-sandbox-controller.service';unit.parent.mkdir(parents=True,exist_ok=True)
    if unit.exists():shutil.copy2(unit,unit.with_name(unit.name+'.before-w09-'+str(time.time_ns())))
    shutil.copy2(ROOT/'docs/remediation/rebase-sandbox-controller.service',unit)
    for command in (['systemctl','--user','daemon-reload'],['systemctl','--user','enable','--now',unit.name],['systemctl','--user','restart',unit.name]):
        subprocess.run(command,capture_output=True,text=True,check=True,timeout=20)
    api_env=ROOT/'backend/.env'
    backupdir=ROOT/'backups';backupdir.mkdir(exist_ok=True)
    backup=backupdir/('backend-env-before-w09-controller-'+str(time.time_ns()))
    shutil.copy2(api_env,backup)
    updates={k:config[k] for k in ('SANDBOX_DISPATCH_KEY','SANDBOX_ATTESTATION_KEY')}
    updates.update(SANDBOX_CONTROLLER_URL='http://127.0.0.1:8093',SANDBOX_RUNTIME='docker-rootless',
        PHASE6_SANDBOX_IMAGE=images[0],PHASE7_SANDBOX_IMAGE=images[1])
    text=api_env.read_text(encoding='utf-8-sig')
    for key,value in updates.items():
        line=key+'='+json.dumps(value)
        pattern=re.compile(r'^'+re.escape(key)+r'=.*$',re.MULTILINE)
        text=pattern.sub(lambda match:line,text) if pattern.search(text) else text.rstrip()+'\n'+line+'\n'
    # Windows control plane reaches its existing PostgreSQL instance locally.
    # The previous WSL gateway host did not authenticate; credentials are kept.
    text=re.sub(r'^(DATABASE_URL=.*@)172\.24\.96\.1(:5432/.*)$',r'\g<1>127.0.0.1\g<2>',text,flags=re.MULTILINE)
    api_env.write_text(text,encoding='utf-8')
    deadline=time.time()+20
    while True:
        try:
            nonce=secrets.token_hex(16)
            request=urllib.request.Request('http://127.0.0.1:8093/v1/rpc',method='POST',headers={'Content-Type':'application/json'},
                data=canonical(seal({'action':'health','runtime':'docker-rootless','nonce':nonce,'expires_at':time.time()+30},config['SANDBOX_DISPATCH_KEY'])))
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=10) as response:
                health=unseal(json.load(response),config['SANDBOX_ATTESTATION_KEY'],expiring=False)
            if health.pop('rpc_nonce')!=nonce:raise ValueError('Controller response replay')
            break
        except Exception:
            if time.time()>deadline:raise
            time.sleep(.2)
    active=subprocess.run(['systemctl','--user','is-active',unit.name],capture_output=True,text=True,timeout=10)
    evidence={'status':'PASS' if active.returncode==0 and health['status']=='ready' else 'BLOCKED',
        'unit':unit.name,'unit_status':active.stdout.strip(),'health':health,'private_configuration_mode':oct(path.stat().st_mode & 0o777),
        'api_configuration_keys_updated':sorted(updates),'api_environment_backup_created':backup.is_file(),
        'control_plane_database_credentials_passed_to_worker':False,'diagnostics_enabled':False,
        'api_restart_required':True,'live_migrations_applied':False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as output:json.dump(evidence,output,indent=2)
    print(json.dumps(evidence),flush=True)
    return 0 if evidence['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
