from pathlib import Path

p6_path = Path("backend/app/services/phase6_service.py")
content = p6_path.read_text(encoding="utf-8")
old_esc = "min(\n                5, 1 + job.max_repair_attempts\n            )"
new_esc = "min(\n                10, 1 + (job.max_repair_attempts or 5)\n            )"
if old_esc in content:
    p6_path.write_text(content.replace(old_esc, new_esc, 1), encoding="utf-8")
    print("Patched escalation limit in phase6_service.py")
else:
    # try single line
    old_esc_s = "min(5, 1 + job.max_repair_attempts)"
    new_esc_s = "min(10, 1 + (job.max_repair_attempts or 5))"
    assert old_esc_s in content, "old_esc not found"
    p6_path.write_text(content.replace(old_esc_s, new_esc_s, 1), encoding="utf-8")
    print("Patched single line escalation limit")

