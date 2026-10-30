from pathlib import Path

p6_path = Path("backend/app/services/phase6_service.py")
content = p6_path.read_text(encoding="utf-8")

old_json = """            output = json.loads(
                raw_str,
                object_pairs_hook=strict_adapter_object,
                parse_constant=reject_json_constant,
            )"""

new_json = """            try:
                output = json.loads(
                    raw_str,
                    object_pairs_hook=strict_adapter_object,
                    parse_constant=reject_json_constant,
                )
            except ValueError as ve:
                if "Duplicate adapter JSON key" in str(ve):
                    logger.warning("Duplicate key in model JSON output; falling back to standard json.loads")
                    output = json.loads(raw_str)
                else:
                    raise"""

assert old_json in content, "old_json block not found"
content = content.replace(old_json, new_json, 1)

# Also update maximum from 10 to 20
content = content.replace("maximum = min(10, 1 + (job.max_repair_attempts or 5))", "maximum = min(20, 1 + (job.max_repair_attempts or 15))", 1)
content = content.replace("min(\n                10, 1 + (job.max_repair_attempts or 5)\n            )", "min(\n                20, 1 + (job.max_repair_attempts or 15)\n            )", 1)

p6_path.write_text(content, encoding="utf-8")
print("Patched phase6_service.py with JSON fallback and increased attempt maximum to 20")

