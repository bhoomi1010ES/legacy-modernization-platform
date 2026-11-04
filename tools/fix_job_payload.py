from pathlib import Path

path = Path("tools/test_full_bootstrap_flow.py")
content = path.read_text(encoding="utf-8")

old_payload = '''            job_payload = {
                "repository_url": "https://localhost:8443/repo.git",
                "source_language": "python",
                "target_framework": "django",
                "budget_limit_usd": 100.0,
            }'''

new_payload = '''            job_payload = {
                "name": "Bootstrap Verification Job",
                "source_repository": "https://localhost:8443/repo.git",
                "source_revision": "main",
                "budget": 15000.0,
            }'''

content = content.replace(old_payload, new_payload, 1)
path.write_text(content, encoding="utf-8")
print("Updated job_payload in test_full_bootstrap_flow.py")

