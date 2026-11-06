import os
import json
from e2b import Sandbox
from app.services.sandbox_harness import HARNESS, HARNESS_VERSION
from app.services.sandbox_reviewer import REVIEWER

api_key = "e2b_2e4f304269fd97e1c7e4b6fd912ec05d5e8a825d"
os.environ["E2B_API_KEY"] = api_key

sb = Sandbox.create(timeout=120)
print("E2B Sandbox started:", sb.sandbox_id)

sample_files = {
    "app/main.py": "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/health')\ndef health():\n    return {'status': 'healthy'}\n",
    "app/__init__.py": ""
}

sample_checks = [
    {"category": "build", "command": ["python", "-m", "compileall", "-q", "."]}
]

payload = {
    "files": sample_files,
    "checks": sample_checks,
    "cases": [],
    "adapter": ["python", "/adapter.py"]
}

try:
    # Ensure /work exists and is writable by user
    sb.commands.run("sudo mkdir -p /work && sudo chown -R $(id -u):$(id -g) /work")
    
    # Write harness and reviewer to sandbox
    sb.files.write("/tmp/harness.py", HARNESS)
    sb.files.write("/tmp/reviewer.py", REVIEWER)
    sb.files.write("/tmp/payload.json", json.dumps(payload))
    sb.files.write("/tmp/rev_payload.json", json.dumps({"files": sample_files}))

    # Run harness
    res = sb.commands.run("python3 /tmp/harness.py < /tmp/payload.json")
    print("HARNESS EXIT:", res.exit_code)
    print("HARNESS STDOUT:", res.stdout)
    if res.stderr:
        print("HARNESS STDERR:", res.stderr)

    # Run reviewer
    res_rev = sb.commands.run("python3 /tmp/reviewer.py < /tmp/rev_payload.json")
    print("REVIEWER EXIT:", res_rev.exit_code)
    print("REVIEWER STDOUT:", res_rev.stdout)
finally:
    sb.kill()
    print("E2B Sandbox killed successfully!")
