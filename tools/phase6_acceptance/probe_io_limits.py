"""Inspect real rootless block I/O throttles using a trusted preflight program."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend/app/services'))
from sandbox_controller import execute_container,INSPECTOR


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise ValueError('Evidence must not be overwritten')
    os.environ['DOCKER_CONTEXT']='rootless'
    source=subprocess.run(['findmnt','-no','SOURCE','-T',str(Path.home()/'.local/share/docker')],capture_output=True,text=True,check=True).stdout.strip()
    os.environ.update(SANDBOX_IO_DEVICE=source,SANDBOX_IO_READ_BPS='10485760',SANDBOX_IO_WRITE_BPS='10485760')
    request={k:uuid.uuid4().hex for k in ('request_id','job_id','attempt_id','_controller_id')}
    request['execution']={'image':'sha256:afad74cbf6c87d0bd550e5b33496713aaeecafb45f052b9dc8bfc279435970f3','runtime':'docker-rootless','timeout':15}
    result=execute_container(request,INSPECTOR,{'adapter':'/adapter.py'},'io-preflight')
    limits=(result.get('observation') or {}).get('cgroup_limits') or {}
    io=limits.get('io.max') or ''
    passed=result.get('exit_code')==0 and all(key+'=10485760' in io for key in ('rbps','wbps')) and result['cleanup']['container_absent']
    evidence={'status':'PASS' if passed else 'BLOCKED','block_device':source,'read_bps':10485760,'write_bps':10485760,'preflight':result}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as output:json.dump(evidence,output,indent=2)
    print(json.dumps(evidence),flush=True);return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
