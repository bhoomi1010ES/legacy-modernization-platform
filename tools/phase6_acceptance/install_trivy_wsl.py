"""User-approved installation of a pinned official Trivy release in WSL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise ValueError('Installation evidence must not be overwritten')
    if platform.system()!='Linux' or platform.machine()!='x86_64':raise ValueError('This reviewed installer requires Linux x86_64')
    version='0.76.1';name=f'trivy_{version}_Linux-64bit.tar.gz'
    base=f'https://github.com/aquasecurity/trivy/releases/download/v{version}/'
    evidence={'release':version,'source':base,'authorization':'User approved Trivy and controller setup in this conversation'}
    def download(url,target,limit):
        request=urllib.request.Request(url,headers={'User-Agent':'Rebase-W09-Provisioner'})
        with urllib.request.urlopen(request,timeout=30) as response,target.open('xb') as output:
            size=0
            while True:
                chunk=response.read(1024*1024)
                if not chunk:break
                size+=len(chunk)
                if size>limit:raise ValueError('Provisioning asset exceeds size limit')
                output.write(chunk)
    with tempfile.TemporaryDirectory(prefix='rebase-trivy-provision-') as folder:
        temp=Path(folder);checks=temp/'checksums.txt';archive=temp/name
        print(json.dumps({'stage':'download_official_release','version':version}),flush=True)
        download(base+f'trivy_{version}_checksums.txt',checks,1048576)
        expected=next(line.split()[0] for line in checks.read_text().splitlines() if line.split()[-1].lstrip('*')==name)
        download(base+name,archive,128*1024*1024)
        actual=hashlib.sha256(archive.read_bytes()).hexdigest()
        if actual!=expected:raise ValueError('Trivy release checksum mismatch')
        binary=Path.home()/'.local/bin/trivy';binary.parent.mkdir(parents=True,exist_ok=True)
        if binary.is_symlink():raise ValueError('Refusing to overwrite a symlink executable')
        with tarfile.open(archive,'r:gz') as package:
            member=package.getmember('trivy')
            if not member.isfile() or member.size>200*1024*1024:raise ValueError('Unexpected Trivy archive member')
            pending=temp/'trivy';pending.write_bytes(package.extractfile(member).read());pending.chmod(0o755)
        if binary.exists():
            backup=binary.with_name('trivy.before-w09-'+str(time.time_ns()));shutil.copy2(binary,backup)
        shutil.copy2(pending,binary)
        evidence.update(archive_sha256=actual,binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),checksum_verified=True)
    env={k:v for k,v in os.environ.items() if k in {'HOME','PATH','LANG','XDG_RUNTIME_DIR'}}
    env['DOCKER_HOST']=f'unix:///run/user/{os.getuid()}/docker.sock'
    result=subprocess.run([str(binary),'--version'],capture_output=True,text=True,timeout=10,env=env)
    evidence['version_output']=result.stdout.strip();evidence['version_exit_code']=result.returncode
    print(json.dumps({'stage':'download_vulnerability_database','version':evidence['version_output']}),flush=True)
    result=subprocess.run([str(binary),'image','--download-db-only','--no-progress'],capture_output=True,text=True,timeout=240,env=env)
    evidence.update(database_download_exit_code=result.returncode,database_download_log=result.stderr[-4000:],status='PASS' if result.returncode==0 else 'BLOCKED')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as output:json.dump(evidence,output,indent=2)
    print(json.dumps(evidence),flush=True)
    return 0 if result.returncode==0 else 1


if __name__=='__main__':raise SystemExit(main())
