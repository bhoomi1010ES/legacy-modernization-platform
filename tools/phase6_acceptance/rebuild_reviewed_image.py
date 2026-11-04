"""Build the reviewed adapter patch over an exact local image, with no network/context secrets."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import uuid


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--base',required=True);parser.add_argument('--tag',required=True);args=parser.parse_args()
    def docker(*argv):
        p=subprocess.run(['docker',*argv],capture_output=True,text=True,timeout=180)
        if p.returncode: raise RuntimeError(p.stderr[-2500:])
        return p.stdout.strip()
    security=json.loads(docker('info','--format','{{json .SecurityOptions}}'))
    if 'name=rootless' not in security: raise ValueError('Only the WSL rootless image builder is allowed')
    identity=docker('image','inspect','--format','{{.Id}}',args.base)
    if identity!=args.base: raise ValueError('Exact immutable local base ID required')
    root=Path(__file__).resolve().parent/'image'
    adapter=(root/'adapter.py').read_bytes()
    alias='rebase/w09-reviewed-base:'+uuid.uuid4().hex
    docker('tag',identity,alias)
    try:
        with tempfile.TemporaryDirectory(prefix='rebase-w09-image-') as folder:
            context=Path(folder)
            (context/'adapter.py').write_bytes(adapter)
            (context/'Dockerfile').write_bytes((root/'Dockerfile.v3').read_bytes())
            output=docker('build','--pull=false','--network=none','--build-arg','BASE='+alias,'--tag',args.tag,str(context))
        image=docker('image','inspect','--format','{{.Id}}',args.tag)
        print(json.dumps({'base_image_digest':identity,'reviewed_image_digest':image,'adapter_sha256':hashlib.sha256(adapter).hexdigest(),'build_output':output[-1000:]},indent=2))
    finally: docker('image','rm',alias)


if __name__=='__main__':main()
