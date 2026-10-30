import json
from pathlib import Path

v_path = Path("artifacts/jobs/eb2bbaa9-90ee-4e9d-b340-5e025594126c/artifacts/VERIFICATION_REPORT_v3.json")
r_path = Path("artifacts/jobs/eb2bbaa9-90ee-4e9d-b340-5e025594126c/artifacts/REVIEW_REPORT_v3.json")

print("="*80)
print("TASK E: INDEPENDENTLY VALIDATE VERIFICATION & REVIEW REPORTS")
print("="*80)

v_data = json.loads(v_path.read_text(encoding="utf-8"))
print(f"1. Verification Report Overview:")
print(f"   Overall Passed: {v_data.get('passed')}")
print(f"   Execution Timestamp: {v_data.get('timestamp')}")
print(f"   Total Duration: {v_data.get('duration_seconds')}s")

checks = v_data.get("checks", [])
print(f"\n2. Verification Checks ({len(checks)}):")
for idx, chk in enumerate(checks, 1):
    print(f"\n   Check #{idx}: {chk.get('name')}")
    print(f"   Command: {chk.get('command')}")
    print(f"   Exit Code: {chk.get('exit_code')}")
    print(f"   Passed: {chk.get('passed')}")
    print(f"   Duration: {chk.get('duration_seconds')}s")
    stdout = chk.get("stdout", "")
    stderr = chk.get("stderr", "")
    if stdout:
        first_line = stdout.strip().splitlines()[0] if stdout.strip() else ""
        print(f"   Stdout summary (len {len(stdout)}): {first_line[:120]}")
    if stderr:
        print(f"   Stderr (len {len(stderr)}): {stderr.strip()[:120]}")

char_results = v_data.get("characterization_results", [])
print(f"\n3. Characterization Scenarios:")
print(f"   Total Scenarios Executed: {len(char_results)}")
passed_cnt = sum(1 for c in char_results if c.get("passed") is True)
failed_cnt = sum(1 for c in char_results if c.get("passed") is False)
print(f"   Passed Scenarios: {passed_cnt}")
print(f"   Failed Scenarios: {failed_cnt}")
print(f"   All 141 Passed?: {passed_cnt == 141 and failed_cnt == 0}")

# Sample some characterization scenarios
print("   Sample Scenarios:")
for s in char_results[:5]:
    print(f"     - ID: {s.get('scenario_id')}, Function: {s.get('function_name')}, Passed: {s.get('passed')}")

# Reviewer report
r_data = json.loads(r_path.read_text(encoding="utf-8"))
print(f"\n4. Reviewer / SAST Report:")
print(json.dumps(r_data, indent=2))

