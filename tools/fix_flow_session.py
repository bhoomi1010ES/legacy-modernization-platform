from pathlib import Path

path = Path("tools/test_full_bootstrap_flow.py")
content = path.read_text(encoding="utf-8")

old_code = '''            # 3b. Login
            login_resp = client.post(
                "/api/v1/auth/login",
                json={"email": reg_payload["email"], "password": reg_payload["password"]},
            )
            assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
            token = login_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            print("4. User logged in successfully.")

            # 3c. Create first job
            job_payload = {
                "repository_url": "https://localhost:8443/repo.git",
                "source_language": "python",
                "target_framework": "django",
                "budget_limit_usd": 100.0,
            }
            job_resp = client.post("/api/v1/jobs", json=job_payload, headers=headers)'''

new_code = '''            # 3b. Login
            login_resp = client.post(
                "/api/v1/auth/login",
                json={"email": reg_payload["email"], "password": reg_payload["password"]},
            )
            assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
            print("4. User logged in successfully via session cookie.")

            # 3c. Create first job
            job_payload = {
                "repository_url": "https://localhost:8443/repo.git",
                "source_language": "python",
                "target_framework": "django",
                "budget_limit_usd": 100.0,
            }
            job_resp = client.post("/api/v1/jobs", json=job_payload)'''

content = content.replace(old_code, new_code, 1)
content = content.replace('headers=headers', '')
path.write_text(content, encoding="utf-8")
print("Updated session handling in test_full_bootstrap_flow.py")

