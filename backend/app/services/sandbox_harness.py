"""Image-owned tool execution protocol. Standard library only; no app credentials."""

HARNESS_VERSION = "w09-harness-v3"
HARNESS = r'''
import base64, datetime, hashlib, importlib.metadata, json, os, pathlib, re, subprocess, sys, time, uuid
import xml.etree.ElementTree as ET
payload=json.load(sys.stdin)
root=pathlib.Path('/work')
root.mkdir(exist_ok=True)
reserved={'pytest','_pytest','mypy','bandit','ruff','sitecustomize','usercustomize'}
inventory={}
for name, content in payload['files'].items():
    rel=pathlib.PurePosixPath(name)
    if not name or rel.is_absolute() or rel.as_posix()!=name or any(p in {'.','..','.git','.env','.aws','.ssh'} or '\\' in p or ':' in p for p in rel.parts):
        raise ValueError('Unsafe snapshot path')
    if rel.parts[0].split('.')[0] in reserved: raise ValueError('Candidate attempts to replace a trusted verification tool')
    path=root.joinpath(*rel.parts)
    path.parent.mkdir(parents=True,exist_ok=True)
    if isinstance(content,str): raw=content.encode('utf-8')
    elif isinstance(content,dict) and set(content)=={'encoding','data','sha256'} and content['encoding']=='base64':
        raw=base64.b64decode(content['data'],validate=True)
        if hashlib.sha256(raw).hexdigest()!=content['sha256']: raise ValueError('Binary content hash mismatch')
    else: raise ValueError('Invalid snapshot entry')
    path.write_bytes(raw)
    inventory[name]=hashlib.sha256(raw).hexdigest()
env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL','HOME','TMPDIR'}}
env.update(PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',HOME='/tmp')
results=[]
for check in payload['checks']:
    started=datetime.datetime.now(datetime.timezone.utc).isoformat(); start=time.monotonic()
    command=check['command']; actual=list(command); tool=pathlib.PurePosixPath(command[0]).name
    report=None; count=None; version='UNKNOWN'; result='NOT_RUN'; stdout=''; stderr=''; code=None
    try:
        if tool in {'python','python3'} and len(command)>2 and command[1]=='-m':
            tool=command[2]
            try: version=importlib.metadata.version(tool)
            except importlib.metadata.PackageNotFoundError:
                if tool=='compileall': version=sys.version.split()[0]
                else: raise FileNotFoundError('Trusted '+tool+' distribution unavailable')
            actual=[sys.executable,'-I','-m',tool,*command[3:]]
            if tool=='pytest':
                report='/tmp/w09-unit-'+uuid.uuid4().hex+'.xml'
                args=['-c','/dev/null','--noconftest','--import-mode=importlib','--junitxml='+report,*command[3:]]
                bootstrap="import pytest,sys;sys.path.append('/work');raise SystemExit(pytest.main("+repr(args)+"))"
                actual=[sys.executable,'-I','-c',bootstrap]
            elif tool=='mypy': actual.insert(4,'--config-file=/dev/null')
            elif tool=='ruff': actual.insert(4,'--isolated')
        elif tool in {'pytest','mypy','bandit','ruff'}:
            raise FileNotFoundError('Use the trusted Python module profile for this tool')
        else:
            v=subprocess.run([command[0],'--version'],cwd='/tmp',capture_output=True,text=True,timeout=5,env=env)
            if v.returncode: raise FileNotFoundError('Tool version unavailable')
            version=(v.stdout or v.stderr).strip()[:500]
        run=subprocess.run(actual,cwd=root,input='',capture_output=True,text=True,timeout=30,shell=False,env=env)
        stdout,stderr=run.stdout[:32768],run.stderr[:32768];code=run.returncode
        result='PASS' if code==0 else 'FAIL'
        if check['category'] in {'unit', 'integration', 'runtime', 'api_compatibility', 'schema'} and tool == 'pytest':
            if report and pathlib.Path(report).is_file():
                suites=ET.parse(report).getroot(); count=sum(1 for _ in suites.iter('testcase'))
            if result=='PASS' and not count:
                result='NOT_RUN';stderr+='\nNo structured executed test cases were reported'
    except FileNotFoundError as exc: stderr=str(exc);result='NOT_RUN'
    except subprocess.TimeoutExpired: stderr='Execution deadline exceeded';result='TIMEOUT'
    results.append(dict(category=check['category'],command=command,tool_name=tool,tool_version=version,started_at=started,
        finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),exit_code=code,duration_ms=(time.monotonic()-start)*1000,
        stdout=stdout,stderr=stderr,logs_hash=hashlib.sha256((stdout+'\n'+stderr).encode()).hexdigest(),
        case_count=count,assertion_count=None,status=result,skipped_reason=stderr if result=='NOT_RUN' else None))
observations=[]
for case in payload['cases']:
    start=time.monotonic(); command=payload['adapter']; actual=list(command)
    if pathlib.PurePosixPath(command[0]).name in {'python','python3'}: actual=[sys.executable,'-I',*command[1:]]
    try:
        run=subprocess.run(actual,cwd=root,input=json.dumps(dict(scenario=case['name'],inputs=case['fixtures'])),capture_output=True,text=True,timeout=30,shell=False,env=env)
        observations.append(dict(test_case_id=case['test_case_id'],command=command,exit_code=run.returncode,duration_ms=(time.monotonic()-start)*1000,stdout=run.stdout[:65536],stderr=run.stderr[:32768],status='OBSERVED' if run.returncode==0 else 'UNOBSERVED'))
    except (subprocess.TimeoutExpired,OSError) as exc:
        observations.append(dict(test_case_id=case['test_case_id'],command=command,exit_code=None,duration_ms=(time.monotonic()-start)*1000,status='UNOBSERVED',stderr=type(exc).__name__))
unchanged=all((root/n).is_file() and hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in inventory.items())
print(json.dumps(dict(checks=results,observations=observations,source_unchanged=unchanged),allow_nan=False))
'''
