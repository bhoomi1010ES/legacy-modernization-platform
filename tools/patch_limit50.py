from pathlib import Path

p = Path("backend/app/services/phase6_service.py")
content = p.read_text(encoding="utf-8")
content = content.replace("maximum = min(30, 1 + (job.max_repair_attempts or 25))", "maximum = min(50, 1 + (job.max_repair_attempts or 40))")
content = content.replace("min(\n                30, 1 + (job.max_repair_attempts or 25)\n            )", "min(\n                50, 1 + (job.max_repair_attempts or 40)\n            )")
p.write_text(content, encoding="utf-8")
print("Updated phase6_service.py max attempt limit to 50")

