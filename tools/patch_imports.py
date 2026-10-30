from pathlib import Path

p6_path = Path("backend/app/services/phase6_service.py")
content = p6_path.read_text(encoding="utf-8")

old_text = "clean_content = (content or '').replace('\\x00', '')"
new_text = """clean_content = (content or '').replace('\\x00', '')
                clean_content = re.sub(
                    r'from\\s+app\\.modules\\.[a-zA-Z0-9_\\-]+\\.([a-zA-Z0-9_]+)\\s+import',
                    r'from .\\1 import',
                    clean_content,
                )"""

assert old_text in content, "old_text not found"
p6_path.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
print("Patched phase6_service.py with relative import normalization")

