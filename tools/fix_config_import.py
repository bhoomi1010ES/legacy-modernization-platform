from pathlib import Path

config_path = Path("backend/app/core/config.py")
content = config_path.read_text(encoding="utf-8")
content = content.replace("from typing import Any, List", "from typing import Any, List, Optional")
config_path.write_text(content, encoding="utf-8")
print("Added Optional to typing import in config.py")

