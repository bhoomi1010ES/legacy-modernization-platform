from pathlib import Path

path = Path("app/services/phase6_service.py")
text = path.read_text(encoding="utf-8")

old_code = 'previous.status not in {"REPAIR_REQUIRED", "BLOCKED", "REJECTED"}'
new_code = 'previous.status not in {"REPAIR_REQUIRED", "BLOCKED", "REJECTED", "WAITING_FOR_HUMAN"}'

assert old_code in text, "old_code not found in phase6_service.py"
text = text.replace(old_code, new_code)
path.write_text(text, encoding="utf-8")
print("Successfully updated phase6_service.py with WAITING_FOR_HUMAN!")

