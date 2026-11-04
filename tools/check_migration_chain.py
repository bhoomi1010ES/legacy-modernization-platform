from pathlib import Path
import re

for p in sorted(Path("backend/alembic/versions").glob("*.py")):
    content = p.read_text(encoding="utf-8")
    rev = re.search(r"revision\s*:\s*str\s*=\s*['\"]([^'\"]+)['\"]", content)
    down = re.search(r"down_revision\s*:\s*Union\[str,\s*None\]\s*=\s*([^\n]+)", content)
    if not down:
        down = re.search(r"down_revision\s*=\s*([^\n]+)", content)
    print(f"{p.name} -> rev={rev.group(1) if rev else '?'}, down={down.group(1).strip() if down else '?'}")

