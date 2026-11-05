"""Frontend and Backend End-to-End Connectivity and Proxy Verification."""

import http.cookiejar
import json
import urllib.request
import uuid

BACKEND_URL = "http://127.0.0.1:8001"
FRONTEND_URL = "http://localhost:3001"


def test_connectivity():
    print("=================================================================")
    print("      Frontend <-> Backend End-to-End Connectivity Test          ")
    print("=================================================================")

    # 1. Direct Backend Connectivity Check
    print(f"\n[1] Checking Backend Direct Readiness at {BACKEND_URL}/openapi.json ...")
    req = urllib.request.Request(f"{BACKEND_URL}/openapi.json")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        print(f"    -> [PASS] Backend responsive (title: '{data.get('info', {}).get('title')}', version: {data.get('info', {}).get('version')})")

    # 2. Frontend HTML Readiness Check
    print(f"\n[2] Checking Frontend Dev Server at {FRONTEND_URL}/ ...")
    req = urllib.request.Request(f"{FRONTEND_URL}/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "<div id=\"root\"></div>" in html or "vite" in html
        print(f"    -> [PASS] Frontend dev server serving React app index (HTTP {resp.status})")

    # 3. Frontend-to-Backend Proxy Verification (Unauthenticated /api/v1/auth/me)
    print(f"\n[3] Checking Frontend Reverse Proxy (/api -> Backend) at {FRONTEND_URL}/api/v1/auth/me ...")
    try:
        req = urllib.request.Request(f"{FRONTEND_URL}/api/v1/auth/me")
        urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as e:
        assert e.code == 401
        body = json.loads(e.read().decode("utf-8"))
        assert body.get("error", {}).get("code") == "UNAUTHORIZED"
        server_header = e.headers.get("server", "")
        print(f"    -> [PASS] Proxy forwarded to uvicorn backend. Response: HTTP 401 UNAUTHORIZED (server: {server_header})")

    # 4. End-to-End User Registration through Frontend Proxy
    unique_suffix = uuid.uuid4().hex[:8]
    test_email = f"connectivity.{unique_suffix}@rebase.io"
    test_password = "SecurePassword2026!#"
    test_name = f"Connectivity User {unique_suffix}"

    print(f"\n[4] Registering User via Frontend Proxy: {test_email} ...")
    reg_payload = json.dumps({
        "email": test_email,
        "password": test_password,
        "full_name": test_name,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{FRONTEND_URL}/api/v1/auth/register",
        data=reg_payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status in (200, 201)
            reg_data = json.loads(resp.read().decode("utf-8"))
            user_id = reg_data.get("user_id")
            print(f"    -> [PASS] User successfully registered via proxy (user_id: {user_id}, role: {reg_data.get('role')})")
    except urllib.error.HTTPError as err:
        print(f"    -> [ERROR] Status: {err.code}, Body: {err.read().decode('utf-8')}")
        raise

    # 5. End-to-End Login & Session Cookie Exchange through Frontend Proxy
    print(f"\n[5] Logging in via Frontend Proxy to establish authenticated session ...")
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

    login_payload = json.dumps({
        "email": test_email,
        "password": test_password,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{FRONTEND_URL}/api/v1/auth/login",
        data=login_payload,
        headers={"Content-Type": "application/json"},
    )
    with opener.open(req, timeout=5) as resp:
        assert resp.status == 200
        login_data = json.loads(resp.read().decode("utf-8"))
        print(f"    -> [PASS] Login successful! Session cookie issued for: {login_data.get('email')}")

    cookies = [c.name for c in cookie_jar]
    print(f"    -> Active Session Cookies: {cookies}")
    assert any("session" in c for c in cookies)

    # 6. Authenticated /api/v1/auth/me Request through Frontend Proxy
    print(f"\n[6] Verifying Authenticated Session via Frontend Proxy at {FRONTEND_URL}/api/v1/auth/me ...")
    req = urllib.request.Request(f"{FRONTEND_URL}/api/v1/auth/me")
    with opener.open(req, timeout=5) as resp:
        assert resp.status == 200
        me_data = json.loads(resp.read().decode("utf-8"))
        assert me_data.get("email") == test_email
        print(f"    -> [PASS] Authenticated user profile retrieved: email='{me_data.get('email')}', role='{me_data.get('role')}'")

    # 7. Query Jobs Catalog through Frontend Proxy
    print(f"\n[7] Querying Jobs Catalog via Frontend Proxy at {FRONTEND_URL}/api/v1/jobs ...")
    req = urllib.request.Request(f"{FRONTEND_URL}/api/v1/jobs")
    with opener.open(req, timeout=5) as resp:
        assert resp.status == 200
        jobs_data = json.loads(resp.read().decode("utf-8"))
        items = jobs_data.get("items", []) if isinstance(jobs_data, dict) else jobs_data
        print(f"    -> [PASS] Jobs catalog queried successfully: {len(items)} jobs returned.")

    print("\n=================================================================")
    print("   ALL 7 CONNECTIVITY & PROXY CHECKS PASSED: 100% OPERATIONAL    ")
    print("=================================================================")


if __name__ == "__main__":
    test_connectivity()
