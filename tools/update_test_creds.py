from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

for rel_path in [
    "backend/tests/test_phase1_auth.py",
    "backend/tests/test_phase1_jobs_and_audit.py",
    "backend/tests/contracts/test_api_integration.py",
    "backend/tests/contracts/test_openapi_contracts.py",
    "backend/tests/contracts/test_phase2_agent_run_api.py",
    "backend/tests/test_github_private_repo.py",
    "backend/tests/test_phase2_stack_detector.py",
    "backend/tests/test_phase2b_tiered_detector.py",
]:
    p = ROOT / rel_path
    if p.exists():
        text = p.read_text(encoding="utf-8")
        if 'alex.morgan@acme.corp", "password": "SecurePassword123!"' in text:
            text = text.replace(
                'alex.morgan@acme.corp", "password": "SecurePassword123!"',
                'alex.morgan@acme.corp", "password": "AdminSecure123!"'
            )
            p.write_text(text, encoding="utf-8")
            print(f"Updated {rel_path}")

print("Done updating test credentials to legitimate password.")

