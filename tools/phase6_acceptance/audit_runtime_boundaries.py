"""Bounded real-Docker audit probes; these are not W09 acceptance results.

Uses only the standard library so it can inspect the WSL daemon without
installing the backend. Candidate marker modules execute only in containers.
"""

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import uuid


ROOT = Path(__file__).resolve().parents[2]


def stamp():
    return datetime.now(timezone.utc).isoformat()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def docker(*args, input=None, timeout=20):
    return subprocess.run(
        ["docker", *args], input=input, capture_output=True, text=True,
        timeout=timeout, check=False,
    )


def docker_value(template):
    result = docker("info", "--format", template)
    if result.returncode:
        raise RuntimeError("Docker info unavailable: " + result.stderr[:300])
    return result.stdout.strip()


PROVENANCE = r'''
import errno, hashlib, importlib.metadata, importlib.util, json, os
from pathlib import Path
import subprocess, sys
report = {"uid": os.getuid(), "gid": os.getgid(), "tools": {}}
for name in ("pytest", "mypy", "bandit", "syft"):
    spec = importlib.util.find_spec(name)
    try:
        version = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        version = None
    report["tools"][name] = {
        "module_origin": spec.origin if spec else None,
        "distribution_version": version,
    }
report["process_security"] = {
    key: value.strip() for key, value in (
        line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines()
        if line.split(":", 1)[0] in {"CapEff", "NoNewPrivs", "Seccomp"}
    )
}
try:
    Path("/w09-rootfs-proof").write_text("bounded audit marker")
    report["readonly_root_enforced"] = False
except OSError as exc:
    report["readonly_root_enforced"] = exc.errno == errno.EROFS
    report["root_write_errno"] = exc.errno
report["docker_socket_present"] = any(Path(p).exists() for p in (
    "/var/run/docker.sock", "/run/docker.sock", "/run/user/1000/docker.sock"
))
report["credential_environment_present"] = any(os.environ.get(k) for k in (
    "DATABASE_URL", "OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "AZURE_CLIENT_SECRET"
))
adapter = Path("/adapter.py")
if adapter.is_file():
    report["adapter_sha256"] = hashlib.sha256(adapter.read_bytes()).hexdigest()
scenarios_path = Path("/scenarios.json")
scenarios = json.loads(scenarios_path.read_text()) if scenarios_path.exists() else {}
report["embedded_expected_scenarios"] = sum(
    isinstance(v, dict) and "expected" in v for v in scenarios.values()
)
chosen = next((k for k, v in scenarios.items() if k != "add" and isinstance(v, dict) and "expected" in v), None)
if chosen and adapter.is_file():
    result = subprocess.run(
        [sys.executable, str(adapter)], cwd="/work",
        input=json.dumps({"scenario": chosen, "inputs": {"__w09_audit": "no_application"}}),
        capture_output=True, text=True, timeout=10,
    )
    try:
        observed = json.loads(result.stdout)
    except ValueError:
        observed = None
    report["adapter_without_application"] = {
        "scenario": chosen,
        "application_directory_empty": not any(Path("/work").iterdir()),
        "exit_code": result.returncode,
        "returned_embedded_expected": observed == {
            "output": scenarios[chosen].get("expected"),
            "side_effects": scenarios[chosen].get("side_effects"),
        },
    }
print(json.dumps(report, sort_keys=True))
'''


def container_probe(image, program, payload, fixture_id):
    name = "w09-audit-" + uuid.uuid4().hex[:16]
    record = {"fixture_id": fixture_id, "container_name": name, "started_at": stamp()}
    try:
        created = docker(
            "create", "--name", name, "--label", "rebase.audit=w09",
            "--pull=never", "--network=none", "--read-only",
            "--memory=256m", "--cpus=1", "--pids-limit=64", "--cap-drop=ALL",
            "--security-opt=apparmor=docker-default", "--security-opt=no-new-privileges",
            "--user=65534:65534", "--log-driver=none",
            "--tmpfs=/work:rw,noexec,nosuid,nodev,size=128m,mode=1777",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=32m", "--interactive",
            "--entrypoint", "/usr/local/bin/python", image, "-I", "-c", program,
        )
        if created.returncode:
            raise RuntimeError("Container create failed: " + created.stderr[:500])
        record["container_id"] = created.stdout.strip()
        inspected = docker("inspect", name)
        inspected.check_returncode()
        info = json.loads(inspected.stdout)[0]
        host = info["HostConfig"]
        record["image_digest"] = info["Image"]
        record["container_configuration"] = {
            "uid_gid": info["Config"]["User"],
            **{key: host.get(key) for key in (
                "Runtime", "NetworkMode", "ReadonlyRootfs", "Memory", "NanoCpus",
                "PidsLimit", "CapDrop", "SecurityOpt", "Tmpfs", "Binds",
            )},
        }
        result = docker("start", "--attach", "--interactive", name, input=payload, timeout=55)
        record.update(
            exit_code=result.returncode,
            stdout_sha256=sha(result.stdout.encode()),
            stderr_sha256=sha(result.stderr.encode()),
            stderr=result.stderr[:2000],
        )
        if result.returncode:
            raise RuntimeError("Container process failed: " + result.stderr[:500])
        record["observation"] = json.loads(result.stdout)
    except Exception as exc:
        record["error"] = type(exc).__name__ + ": " + str(exc)[:1000]
    finally:
        removed = docker("rm", "--force", name)
        absent = docker("inspect", name)
        record["cleanup"] = {
            "remove_exit_code": removed.returncode,
            "container_absent": absent.returncode != 0,
        }
        record["finished_at"] = stamp()
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image):
        raise ValueError("A local immutable image ID is required")
    if args.output.exists():
        raise ValueError("Refusing to overwrite existing audit evidence")
    security = json.loads(docker_value("{{json .SecurityOptions}}"))
    if "name=rootless" not in security or not any(s.startswith("name=seccomp") for s in security):
        raise RuntimeError("Audit requires actual rootless Docker with seccomp")
    image = docker("image", "inspect", "--format", "{{.Id}}", args.image)
    if image.returncode or image.stdout.strip() != args.image:
        raise RuntimeError("Configured immutable image is unavailable locally")
    source_path = ROOT / "backend/app/services/phase6_sandbox.py"
    source = source_path.read_bytes()
    tree = ast.parse(source.decode("utf-8-sig"))
    harness = next(
        ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "HARNESS" for target in node.targets)
    )
    provenance = container_probe(args.image, PROVENANCE, None, "tool-provenance-and-adapter-without-app")
    marker = "W09_AUDIT_MARKER_ONLY_NO_REAL_CHECK"
    payload = {
        "files": {name + ".py": "print(" + repr(marker) + ")\n" for name in ("pytest", "mypy", "bandit")},
        "checks": [
            {"category": "build", "command": ["python", "-m", "compileall", "-q", "."]},
            {"category": "unit", "command": ["python", "-m", "pytest", "/acceptance/test_calc.py", "-q"]},
            {"category": "static", "command": ["python", "-m", "mypy", "."]},
            {"category": "security", "command": ["python", "-m", "bandit", "-r", "."]},
        ],
        "adapter": ["python", "/adapter.py"], "cases": [],
    }
    shadowing = container_probe(args.image, harness, json.dumps(payload), "candidate-tool-module-shadowing")
    checks = shadowing.get("observation", {}).get("checks", [])
    affected = [c["category"] for c in checks if c.get("exit_code") == 0 and marker in c.get("stdout", "")]
    report = {
        "scope": "Bounded source audit probes only; not full W09 acceptance or job verification",
        "created_at": stamp(), "source_sha256": sha(source), "harness_sha256": sha(harness.encode()),
        "daemon": {
            "context": docker("context", "show").stdout.strip(),
            "version": docker_value("{{.ServerVersion}}"),
            "security_options": security,
            "default_runtime": docker_value("{{.DefaultRuntime}}"),
            "registered_runtime_names": sorted(json.loads(docker_value("{{json .Runtimes}}"))),
        },
        "runs": [provenance, shadowing],
        "findings": {
            "candidate_tool_shadowing_reproduced": set(affected) == {"unit", "static", "security"},
            "affected_check_categories": affected,
            "embedded_expected_without_application": provenance.get("observation", {}).get("adapter_without_application", {}),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"evidence": str(args.output), "daemon": report["daemon"], "findings": report["findings"],
        "run_status": [{"fixture": r["fixture_id"], "exit_code": r.get("exit_code"), "error": r.get("error"), "cleanup": r["cleanup"]} for r in report["runs"]]}, indent=2))


if __name__ == "__main__":
    main()
