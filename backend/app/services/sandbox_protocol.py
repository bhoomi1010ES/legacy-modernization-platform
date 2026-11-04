"""Narrow signed execution capabilities; deliberately independent of app settings/DB."""

import hashlib
import hmac
import json
import re
import time
from pathlib import PurePosixPath

PROTOCOL_VERSION = "sandbox-rpc-v1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def seal(payload, key):
    if not isinstance(key, str) or len(key) < 32:
        raise ValueError("A separate sandbox signing key of at least 32 characters is required")
    return {"payload": payload, "signature": hmac.new(key.encode(), canonical(payload), hashlib.sha256).hexdigest()}


def unseal(envelope, key, *, expiring=True):
    if not isinstance(envelope, dict) or set(envelope) != {"payload", "signature"}:
        raise ValueError("Invalid signed envelope")
    expected = seal(envelope["payload"], key)["signature"]
    if not isinstance(envelope["signature"], str) or not hmac.compare_digest(expected, envelope["signature"]):
        raise ValueError("Sandbox signature does not match")
    payload = envelope["payload"]
    if expiring and not time.time() < float(payload.get("expires_at", 0)) <= time.time() + 900:
        raise ValueError("Sandbox capability is expired or exceeds its lifetime")
    return payload


def approved_command(command, *, adapter=False):
    if not isinstance(command, list) or not command or len(command) > 64 or not all(isinstance(s, str) and s and not any(c in s for c in (';', '|', '&', '`', '$', '\n', '\r', '\x00')) for s in command):
        return False
    from pathlib import PurePosixPath
    tool = PurePosixPath(command[0]).name
    if adapter:
        return tool in {"python", "python3"} and len(command) == 2 and command[1].startswith("/") and '..' not in PurePosixPath(command[1]).parts and PurePosixPath(command[1]).parts[1] not in {"work", "tmp"} and command[1].endswith('.py')
    if tool in {"python", "python3"}:
        if '-p' in command and not all(i + 1 < len(command) and command[i + 1] == 'no:cacheprovider' for i, s in enumerate(command) if s == '-p'):
            return False
        return len(command) >= 3 and command[1] == '-m' and command[2] in {"compileall", "pytest", "mypy", "ruff", "bandit"} and not any(s in command for s in ('-c', '--override-ini', '--config-file', '--config'))
    if tool == 'syft':
        return command in (["syft", "version", "-o", "json"], ["syft", "scan", "dir:/work", "-o", "syft-json"])
    if tool in {'trivy', 'pip-audit', 'pip-licenses', 'licensecheck'}:
        # Exact executable profiles only. These run in the isolated build image;
        # absent executables become NOT_RUN in the harness and cannot pass.
        return tool == 'trivy' and command in (
            ['trivy', 'fs', '--scanners', 'vuln', '--offline-scan', '/work'],
            ['trivy', 'fs', '--scanners', 'misconfig', '--offline-scan', '/work'],
        ) or tool == 'pip-audit' and command == ['pip-audit', '--strict'] or \
            tool == 'pip-licenses' and command == ['pip-licenses', '--format=json'] or \
            tool == 'licensecheck' and command == ['licensecheck', '--fail-on', 'GPL']
    if tool == 'npm':
        return (len(command) == 3 and command[1] == 'run' and command[2] in {'build', 'test', 'lint', 'typecheck', 'security', 'api-compatibility', 'license-check'}) or command == ['npm', 'audit', '--offline']
    return tool == 'tsc' and command == ['tsc', '--noEmit']


def validate_check_profile(checks, *, system=False, schema_required=False):
    """Reject incomplete or mislabeled profiles before creating a worker lease."""
    categories = [item.get('category') for item in checks]
    required = {'build', 'unit', 'integration', 'static', 'security', 'dependency',
                'license', 'runtime', 'api_compatibility'} if system else {
                    'build', 'unit', 'static', 'security', 'dependency', 'license',
                    'runtime', 'integration', 'api_compatibility'}
    if schema_required:
        required.add('schema')
    if not required.issubset(categories):
        return False
    if len({canonical(item.get('command')) for item in checks}) != len(checks):
        return False
    if any(not approved_command(item.get('command')) for item in checks):
        return False
    for item in checks:
        category = item['category']
        command = item['command']
        tool = PurePosixPath(command[0]).name
        module = command[2] if tool in {'python', 'python3'} and len(command) > 2 and command[1] == '-m' else None
        if category == 'build' and not (module == 'compileall' or tool in {'npm', 'tsc'}):
            return False
        if category == 'unit' and module != 'pytest' and command[:2] != ['npm', 'run']:
            return False
        if category == 'integration' and (module == 'compileall' or tool == 'compileall'):
            return False
        if category == 'static' and not (module in {'mypy', 'ruff'} or tool == 'tsc' or command == ['npm', 'run', 'typecheck'] or command == ['npm', 'run', 'lint']):
            return False
        if category == 'security' and not (module == 'bandit' or tool == 'trivy' or command == ['npm', 'run', 'security']):
            return False
        if category == 'dependency' and not (tool in {'trivy', 'pip-audit'} or command == ['npm', 'audit', '--offline']):
            return False
        if category == 'license' and not (tool in {'pip-licenses', 'licensecheck'} or command == ['npm', 'run', 'license-check']):
            return False
        if category == 'runtime' and not (module == 'pytest' or command == ['npm', 'run', 'test']):
            return False
        if category == 'api_compatibility' and not (module == 'pytest' or command == ['npm', 'run', 'api-compatibility']):
            return False
        if category == 'schema' and module == 'compileall':
            return False
    return True


def validate_execution(payload, images):
    from pathlib import PurePosixPath
    for field in ('request_id', 'job_id', 'attempt_id', 'candidate_hash', 'suite_hash'):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', str(payload.get(field, ''))):
            raise ValueError('Invalid execution binding: ' + field)
    body = payload['execution']
    if body.get('purpose','VERIFICATION') not in {'VERIFICATION','CONTAINMENT_DIAGNOSTIC'}:
        raise ValueError('Unknown execution purpose')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', body.get('image', '')) or body['image'] not in images:
        raise ValueError('Image is not an operator-approved immutable local image')
    if body.get('runtime') not in {'docker-rootless', 'gvisor-rootless', 'e2b-microvm'}:
        raise ValueError('Unverified runtime policy')
    if not 1 <= int(body.get('timeout', 0)) <= 600:
        raise ValueError('Invalid execution deadline')
    if len(body.get('files', {})) > 50000 or len(canonical(body)) > 16 * 1024 * 1024:
        raise ValueError('Execution snapshot exceeds limits')
    for name in body.get('files', {}):
        p = PurePosixPath(name)
        devices = {'con','prn','aux','nul',*(f'com{i}' for i in range(1,10)),*(f'lpt{i}' for i in range(1,10))}
        controls = {'.git','.gitmodules','.gitattributes','.env','.aws','.ssh','.npmrc','.pypirc','.netrc'}
        if not name or p.is_absolute() or p.as_posix() != name or any(
            x in {'.','..'} or x.lower() in controls or x.lower().startswith('.env.') or
            '\\' in x or ':' in x or any(ord(c)<32 for c in x) or x.rstrip(' .')!=x or
            x.split('.')[0].lower() in devices for x in p.parts
        ):
            raise ValueError('Unsafe candidate path')
        content=body['files'][name]
        if not isinstance(content,str) and not (isinstance(content,dict) and set(content)=={'encoding','data','sha256'} and content['encoding']=='base64'):
            raise ValueError('Only regular file contents are accepted; links and devices are forbidden')
    if not approved_command(body.get('adapter'), adapter=True):
        raise ValueError('Unapproved adapter command')
    checks = body.get('checks', [])
    if not isinstance(checks, list) or len(checks) > 32 or not all(approved_command(c.get('command')) for c in checks):
        raise ValueError('Unapproved check command')
    for check in checks:
        cmd = check['command']
        if check['category'] == 'unit' and not (cmd[:3] == ['python', '-m', 'pytest'] or cmd[:3] == ['python3', '-m', 'pytest']):
            raise ValueError('Unit checks require a trusted test runner with structured case evidence')
        if check['category'] != 'build' and cmd[:3] in (['python', '-m', 'compileall'], ['python3', '-m', 'compileall']):
            raise ValueError('Compile checks cannot be mislabeled as another verification category')
