import os
import json
from e2b import Sandbox
from app.services.sandbox_harness import HARNESS, HARNESS_VERSION
from app.services.sandbox_reviewer import REVIEWER

api_key = "e2b_2e4f304269fd97e1c7e4b6fd912ec05d5e8a825d"
os.environ["E2B_API_KEY"] = api_key

sb = Sandbox.create(timeout=180)
print("E2B Sandbox started:", sb.sandbox_id)

sample_files = {
    "app/main.py": "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/health')\ndef health():\n    return {'status': 'healthy'}\n",
    "app/__init__.py": "",
    "tests/test_smoke.py": "def test_smoke():\n    assert True\n"
}

checks = [
    {"category": "build", "command": ["python", "-m", "compileall", "-q", "."]},
    {"category": "unit", "command": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]},
    {"category": "integration", "command": ["python", "-m", "pytest", "-k", "smoke", "-q", "-p", "no:cacheprovider"]},
    {"category": "static", "command": ["python", "-m", "mypy", "--cache-dir=/tmp/mypy-cache", "--check-untyped-defs", "--explicit-package-bases", "."]},
    {"category": "security", "command": ["python", "-m", "bandit", "-r", "app", "-q"]},
    {"category": "dependency", "command": ["pip-audit", "--strict"]},
    {"category": "license", "command": ["pip-licenses", "--format=json"]},
    {"category": "runtime", "command": ["python", "-m", "pytest", "-k", "smoke", "-q", "-p", "no:cacheprovider"]},
    {"category": "api_compatibility", "command": ["python", "-m", "pytest", "-k", "smoke", "-q", "-p", "no:cacheprovider"]},
]

payload = {
    "files": sample_files,
    "checks": checks,
    "cases": [],
    "adapter": ["python", "/adapter.py"]
}

try:
    # 1. Setup work dir & config
    sb.commands.run("sudo mkdir -p /work && sudo chown -R $(id -u):$(id -g) /work")
    sb.commands.run("echo '[mypy]\nignore_missing_imports = True' > /tmp/mypy.ini")
    
    # 2. Upgrade pip, setuptools, certifi to avoid audit vulnerabilities & install check tools
    sb.commands.run("python3 -m pip install -q -U pip setuptools certifi pytest mypy bandit pip-audit pip-licenses")
    
    # 3. Patch harness to use /tmp/mypy.ini instead of /dev/null
    patched_harness = HARNESS.replace("--config-file=/dev/null", "--config-file=/tmp/mypy.ini")
    
    sb.files.write("/tmp/harness.py", patched_harness)
    sb.files.write("/tmp/payload.json", json.dumps(payload))
    sb.files.write("/tmp/reviewer.py", REVIEWER)
    sb.files.write("/tmp/rev_payload.json", json.dumps({"files": sample_files}))

    # 4. Run harness
    res = sb.commands.run("python3 /tmp/harness.py < /tmp/payload.json")
    print("HARNESS EXIT:", res.exit_code)
    obs = json.loads(res.stdout)
    print("CHECKS SUMMARY:")
    for c in obs.get("checks", []):
        print(f"  {c['category']}: {c['status']} (exit: {c['exit_code']})")
        if c.get("stderr"):
            print("    stderr:", c["stderr"][:200])

    # 5. Run reviewer
    res_rev = sb.commands.run("python3 /tmp/reviewer.py < /tmp/rev_payload.json")
    print("REVIEWER EXIT:", res_rev.exit_code)
    print("REVIEWER STDOUT:", res_rev.stdout)
finally:
    sb.kill()
    print("E2B Sandbox killed successfully!")

