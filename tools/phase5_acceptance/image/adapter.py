"""Reviewed Go/Fiber observer. It captures only real HTTP and PostgreSQL effects."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


def fail(message):
    sys.stderr.write(message[:1200] + "\n")
    raise SystemExit(78)


def command(args, *, env=None, timeout=15):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env, shell=False)
    if result.returncode:
        raise RuntimeError("approved characterization command failed: " + " ".join(args[:3]) + ": " + result.stderr[-600:])
    return result.stdout.strip()


def verify_source_snapshot():
    manifest = json.loads(Path("/source-manifest.json").read_text())
    expected = manifest.get("files")
    if not isinstance(expected, dict) or not expected:
        raise RuntimeError("reviewed source manifest is invalid")
    manifest_hash = hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if manifest_hash != manifest.get("snapshot_sha256") or manifest.get("source_commit") != os.environ.get("REBASE_SOURCE_COMMIT"):
        raise RuntimeError("image source commit or manifest digest binding is invalid")
    actual = {}
    actual_names = set()
    for path in Path("/work").rglob("*"):
        if path.is_symlink():
            raise RuntimeError("symlink in characterization source workspace")
        if path.is_file():
            actual_names.add(path.relative_to("/work").as_posix())
    if actual_names != set(expected):
        raise RuntimeError("candidate source inventory differs from the image-bound manifest")
    for name in expected:
        rel = PurePosixPath(name)
        path = Path("/work").joinpath(*rel.parts)
        if rel.is_absolute() or rel.as_posix() != name or any(part in {".", ".."} for part in rel.parts) or path.is_symlink() or not path.is_file():
            raise RuntimeError("candidate source inventory differs from the image-bound manifest")
        actual[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError("candidate source hashes differ from the image-bound source commit")
    if any(p.is_file() for p in Path("/work").glob("bin/main")):
        raise RuntimeError("prebuilt executable unexpectedly entered the source workspace")
    return manifest["source_commit"], manifest["snapshot_sha256"]


def request(method, path, data=None, token=None):
    headers = {"Accept": "application/json"}
    body = None
    if data is not None:
        body = json.dumps(data, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request("http://127.0.0.1:8080" + path, data=body, headers=headers, method=method)
    try:
        response = urllib.request.urlopen(req, timeout=5)
        status, text = response.status, response.read(32768).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status, text = exc.code, exc.read(32768).decode("utf-8", "replace")
    try:
        value = json.loads(text)
    except ValueError:
        value = text[:1000]
    return {"status": status, "body": value}


def sql(query):
    return command(["psql", "-X", "-qAt", "-F", "\t", "-h", "127.0.0.1", "-p", "5432", "-U", "postgres", "-d", "crud_test", "-c", query], env={**os.environ, "PGPASSWORD": ""})


def db_users():
    rows = sql("SELECT id, COALESCE(username,''), COALESCE(name,''), COALESCE(email,''), COALESCE(to_char(date AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'),''), COALESCE(city,''), COALESCE(country,'') FROM users ORDER BY id")
    parsed = []
    for line in filter(None, rows.splitlines()):
        fields = line.split("\t")
        parsed.append(dict(zip(("id", "username", "name", "email", "date", "city", "country"), fields)))
    return parsed


def run_case(module):
    if module == "bootstrap":
        response = request("GET", "/swagger/index.html")
        effects = {"users": db_users(), "tables": sql("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name").splitlines()}
        return {"output": {"swagger_status": response["status"], "content_type": "text/html"}, "side_effects": effects}
    if module == "database":
        schema = sql("SELECT column_name || ':' || data_type || ':' || is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name='users' ORDER BY ordinal_position").splitlines()
        return {"output": {"table": "users", "columns": schema}, "side_effects": {"users": db_users()}}
    if module == "middleware":
        before = db_users()
        denied = request("GET", "/api/users")
        after = db_users()
        return {"output": {"unauthenticated_status": denied["status"], "body": denied["body"]}, "side_effects": {"before": before, "after": after}}
    if module == "repository":
        user = {"username": "characterization-user", "name": "Replay User", "email": "replay@example.test", "date": "2000-01-02", "city": "Test City", "country": "Testland", "password": "Synthetic-Replay-Password-1"}
        created = request("POST", "/api/user", user)
        login = request("POST", "/api/login", {"username": user["username"], "password": user["password"]})
        token = login["body"].get("token") if isinstance(login["body"], dict) else None
        authorized = request("GET", "/api/users", token=token) if token else {"status": 0, "body": None}
        return {"output": {"create_status": created["status"], "create_body": created["body"], "login_status": login["status"], "authorized_list_status": authorized["status"]}, "side_effects": {"users": db_users()}}
    if module == "images":
        fail("UNOBSERVED: no image behavior is declared in the Go/Fiber routes; static image files are not browser behavior evidence")
    if module == "frontend":
        fail("UNOBSERVED: a pinned browser/DOM runtime and controlled Next.js dependency build are required; static HTML or asset inspection is not behavioral evidence")
    fail("UNOBSERVED: no reviewed scenario mapping exists for module " + str(module))


def main():
    req = json.load(sys.stdin)
    if set(req) != {"scenario", "inputs"} or not isinstance(req["inputs"], dict):
        raise ValueError("unsupported characterization request")
    module = req["inputs"].get("module", "")
    if not isinstance(module, str) or not module.startswith("mod_"):
        raise ValueError("expected frozen G2 module fixture")
    slug = module.removeprefix("mod_").split("_")[0]
    source_commit, source_snapshot = verify_source_snapshot()
    pg_bins = sorted(Path("/usr/lib/postgresql").glob("*/bin"))
    if not pg_bins:
        raise RuntimeError("PostgreSQL server binaries are missing")
    bindir = str(pg_bins[-1])
    pgdata = Path("/work/pgdata")
    pgdata.mkdir(mode=0o700, exist_ok=True)
    command([bindir + "/initdb", "-D", str(pgdata), "--username=postgres", "--auth-local=trust", "--auth-host=trust"])
    command([bindir + "/pg_ctl", "-D", str(pgdata), "-o", "-h 127.0.0.1 -p 5432 -k /tmp -c shared_buffers=32MB -c max_connections=16 -c fsync=off -c synchronous_commit=off", "-w", "start"], timeout=25)
    command([bindir + "/createdb", "-h", "127.0.0.1", "-p", "5432", "-U", "postgres", "crud_test"])
    secret = "synthetic-characterization-only-key-3f08c646f6c5"
    env = {"PATH": os.environ["PATH"], "HOME": "/tmp", "APP_ENV": "characterization", "DB_HOST": "127.0.0.1", "DB_PORT": "5432", "DB_USER": "postgres", "DB_PASS": "", "DB_SSLMODE": "disable", "DB_NAME": "crud_test", "SECRET_JWT": secret, "GOMAXPROCS": "1"}
    with open("/tmp/legacy-app.log", "w", encoding="utf-8") as logs:
        app = subprocess.Popen(["/app/legacy"], cwd="/work", env=env, stdin=subprocess.DEVNULL, stdout=logs, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            ready = False
            for _ in range(100):
                if app.poll() is not None:
                    raise RuntimeError("legacy application exited during startup")
                try:
                    with socket.create_connection(("127.0.0.1", 8080), timeout=0.1):
                        ready = True
                        break
                except OSError:
                    time.sleep(0.1)
            if not ready:
                raise TimeoutError("legacy Fiber application did not bind its loopback port")
            result = run_case(slug)
            result["side_effects"]["source_commit"] = source_commit
            result["side_effects"]["source_snapshot_sha256"] = source_snapshot
            json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"), allow_nan=False)
        finally:
            if app.poll() is None:
                os.killpg(app.pid, signal.SIGTERM)
                try:
                    app.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(app.pid, signal.SIGKILL)
                    app.wait(timeout=3)
            try:
                subprocess.run([bindir + "/pg_ctl", "-D", str(pgdata), "-m", "immediate", "-w", "stop"], capture_output=True, timeout=8, check=False)
            except Exception:
                pass
            logs.flush()
            text = Path("/tmp/legacy-app.log").read_text(errors="replace")
            if secret in text:
                Path("/tmp/legacy-app.log").write_text(text.replace(secret, "[REDACTED]"))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write(type(exc).__name__ + ": " + str(exc)[:1000] + "\n")
        raise
