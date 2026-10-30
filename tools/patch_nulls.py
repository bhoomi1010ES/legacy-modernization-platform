from pathlib import Path

# 1. Patch phase6_service.py
p6_path = Path("backend/app/services/phase6_service.py")
content = p6_path.read_text(encoding="utf-8")
old_p6 = "normalized_files[clean_key] = content"
new_p6 = "clean_content = (content or '').replace('\\x00', '')\n                normalized_files[clean_key] = clean_content"
assert old_p6 in content, "old_p6 not found"
p6_path.write_text(content.replace(old_p6, new_p6, 1), encoding="utf-8")
print("Patched phase6_service.py")

# 2. Patch reviewer_agent.py
rev_path = Path("backend/app/services/reviewer_agent.py")
rev_content = rev_path.read_text(encoding="utf-8")
old_rev = "tree = ast.parse(source)"
new_rev = "tree = ast.parse(source.replace('\\x00', ''))"
assert old_rev in rev_content, "old_rev not found"
rev_path.write_text(rev_content.replace(old_rev, new_rev, 1), encoding="utf-8")
print("Patched reviewer_agent.py")

