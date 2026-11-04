"""Launch the standalone Linux controller with an explicit credential-free environment."""
import argparse
import json
import os
from pathlib import Path
import stat
import sys


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,required=True);args=parser.parse_args()
    metadata=args.config.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid!=os.getuid() or metadata.st_mode & 0o077:
        raise SystemExit('Controller configuration must be a private regular file owned by this Linux user (chmod 600)')
    config=json.loads(args.config.read_text())
    required={'SANDBOX_DISPATCH_KEY','SANDBOX_ATTESTATION_KEY','SANDBOX_ALLOWED_IMAGES','SANDBOX_ALLOWED_ADAPTER_HASHES'}
    allowed=required|{'SANDBOX_IO_DEVICE','SANDBOX_IO_READ_BPS','SANDBOX_IO_WRITE_BPS'}
    if not required<=set(config) or set(config)-allowed:
        raise SystemExit('Unexpected or missing controller configuration; DB/provider/cloud credentials are forbidden')
    if any(not isinstance(config[k],str) or len(config[k])<32 for k in ('SANDBOX_DISPATCH_KEY','SANDBOX_ATTESTATION_KEY')) or config['SANDBOX_DISPATCH_KEY']==config['SANDBOX_ATTESTATION_KEY']:
        raise SystemExit('Distinct dispatch and attestation keys of at least 32 characters are required')
    environment={'PATH':str(Path.home()/'.local/bin')+':/usr/local/bin:/usr/bin:/bin','HOME':str(Path.home()),'LANG':'C.UTF-8',
        'XDG_RUNTIME_DIR':f'/run/user/{os.getuid()}','DOCKER_HOST':f'unix:///run/user/{os.getuid()}/docker.sock'}
    environment.update({k:json.dumps(v) if isinstance(v,list) else str(v) for k,v in config.items()})
    state=Path.home()/'.local/state/rebase/sandbox-controller.sqlite'
    state.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.execve(sys.executable,[sys.executable,str(Path(__file__).with_name('sandbox_controller.py')),
        '--host','127.0.0.1','--port','8093','--state',str(state)],environment)


if __name__=='__main__':main()
