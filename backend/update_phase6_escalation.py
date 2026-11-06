from pathlib import Path

path = Path("app/services/phase6_service.py")
text = path.read_text(encoding="utf-8")

old_code = '''        maximum = min(50, 1 + (job.max_repair_attempts or 40))
        if last and (last.attempt_number >= maximum or last.status == "WAITING_FOR_HUMAN"):
            raise ConflictException(
                "Repair attempt limit exhausted; human escalation required"
            )'''

new_code = '''        maximum = min(50, 1 + (job.max_repair_attempts or 40))
        if last and last.attempt_number >= maximum:
            raise ConflictException(
                "Repair attempt limit exhausted; human escalation required"
            )
        if last and last.status == "WAITING_FOR_HUMAN" and not (previous and rationale):
            raise ConflictException(
                "Module is waiting for human review; provide review rationale to proceed with repair"
            )'''

assert old_code in text or old_code.replace("\n", "\r\n") in text, "old_code not found in phase6_service.py"
text = text.replace(old_code, new_code)
text = text.replace(old_code.replace("\n", "\r\n"), new_code.replace("\n", "\r\n"))
path.write_text(text, encoding="utf-8")
print("Successfully updated phase6_service.py!")

