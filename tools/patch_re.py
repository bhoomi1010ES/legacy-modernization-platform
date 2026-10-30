from pathlib import Path

p = Path("backend/app/services/phase6_service.py")
content = p.read_text(encoding="utf-8")
old_import = "import json\nimport uuid"
new_import = "import json\nimport re\nimport uuid"
assert old_import in content, "old_import not found"
p.write_text(content.replace(old_import, new_import, 1), encoding="utf-8")
print("Added import re to phase6_service.py")

