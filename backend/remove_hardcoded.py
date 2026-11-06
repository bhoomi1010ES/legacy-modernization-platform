from pathlib import Path

path = Path("app/core/config.py")
text = path.read_text(encoding="utf-8")
text = text.replace('        "convert its backend into fastapi": make_profile("python-fastapi-v1"),\n', '')
text = text.replace('        "convert its backend into fastapi": make_profile("python-fastapi-v1"),\r\n', '')
path.write_text(text, encoding="utf-8")
print("Done removing hardcoded string from config.py!")
