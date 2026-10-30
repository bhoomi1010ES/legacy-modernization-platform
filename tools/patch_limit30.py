from pathlib import Path

p = Path("backend/app/services/phase6_service.py")
content = p.read_text(encoding="utf-8")
content = content.replace("maximum = min(20, 1 + (job.max_repair_attempts or 15))", "maximum = min(30, 1 + (job.max_repair_attempts or 25))")
content = content.replace("min(\n                20, 1 + (job.max_repair_attempts or 15)\n            )", "min(\n                30, 1 + (job.max_repair_attempts or 25)\n            )")
p.write_text(content, encoding="utf-8")
print("Updated phase6_service.py max attempt limit to 30")

