"""Controlled WSL API reload and browser-proxy readiness probe."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit, urlunsplit
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path('/mnt/c/Users/lenovo/Desktop/rebase')
BACKEND = ROOT / 'backend'
PYTHON = Path('/home/lenovo/.venvs/rebase-backend/bin/python')
sys.path.insert(0, str(BACKEND))


def get(url):
    try:
        with urlopen(url, timeout=5) as response:
            return response.status, response.read(4096).decode('utf-8', 'replace')
    except HTTPError as exc:
        return exc.code, exc.read(4096).decode('utf-8', 'replace')


def main():
    if not PYTHON.is_file():
        raise SystemExit('WSL backend virtualenv is missing')
    from app.core.config import settings
    matches = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / 'cmdline').read_bytes().replace(b'\0', b' ').decode('utf-8', 'replace')
        except (OSError, ProcessLookupError):
            continue
        if '/home/lenovo/.venvs/rebase-backend/bin/python -m uvicorn app.main:app' in command and '--port 8001' in command:
            matches.append((int(entry.name), command))
    if len(matches) != 1:
        raise SystemExit(f'Expected one identifiable WSL API process on port 8001; found {len(matches)}')
    old_pid, _ = matches[0]
    os.kill(old_pid, signal.SIGTERM)
    deadline = time.time() + 20
    while Path(f'/proc/{old_pid}').exists() and time.time() < deadline:
        time.sleep(.2)
    if Path(f'/proc/{old_pid}').exists():
        raise SystemExit('Existing WSL API did not stop cleanly; replacement was not started')

    log_dir = BACKEND / '.test_runs' / ('w09-wsl-api-' + str(int(time.time())))
    log_dir.mkdir(parents=True, exist_ok=False)
    log = (log_dir / 'uvicorn.log').open('ab', buffering=0)
    route = subprocess.run(['ip', 'route', 'show', 'default'], capture_output=True, text=True, check=True).stdout.split()
    if len(route) < 3 or route[0] != 'default' or route[1] != 'via':
        raise SystemExit('WSL gateway is unavailable; backend launch blocked')
    gateway = route[2]
    parsed = urlsplit(settings.DATABASE_URL)
    if not parsed.hostname or not parsed.port or parsed.scheme not in {'postgresql', 'postgresql+asyncpg'}:
        raise SystemExit('Expected a configured PostgreSQL URL; no credentials were printed')
    userinfo = parsed.netloc.rpartition('@')[0]
    netloc = (userinfo + '@' if '@' in parsed.netloc else '') + f'{gateway}:{parsed.port}'
    env = os.environ.copy()
    env['DATABASE_URL'] = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    process = subprocess.Popen(
        [str(PYTHON), '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8001', '--log-level', 'warning'],
        cwd=BACKEND, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True, env=env,
    )
    health = readiness = frontend_health = frontend_readiness = None
    deadline = time.time() + 45
    while time.time() < deadline:
        try:
            health = get('http://127.0.0.1:8001/api/v1/health')
            if health[0] == 200:
                readiness = get('http://127.0.0.1:8001/api/v1/readiness')
                frontend_health = get('http://127.0.0.1:3000/api/v1/health')
                frontend_readiness = get('http://127.0.0.1:3000/api/v1/readiness')
                if frontend_health[0] == 200:
                    break
        except (URLError, TimeoutError):
            pass
        if process.poll() is not None:
            break
        time.sleep(.5)
    evidence = {
        'old_pid': old_pid,
        'new_pid': process.pid,
        'database_host': gateway,
        'health': {'status_code': health[0], 'body': health[1]} if health else None,
        'readiness': {'status_code': readiness[0], 'body': readiness[1]} if readiness else None,
        'frontend_proxy_health': {'status_code': frontend_health[0], 'body': frontend_health[1]} if frontend_health else None,
        'frontend_proxy_readiness': {'status_code': frontend_readiness[0], 'body': frontend_readiness[1]} if frontend_readiness else None,
        'log': str(log_dir / 'uvicorn.log'),
    }
    print(json.dumps(evidence))
    return 0 if health and health[0] == 200 and frontend_health and frontend_health[0] == 200 else 1


if __name__ == '__main__':
    raise SystemExit(main())
