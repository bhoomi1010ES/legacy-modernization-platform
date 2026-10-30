from pathlib import Path

path = Path("backend/app/services/phase6_workspace.py")
content = path.read_text(encoding="utf-8")
normalized = content.replace("\r\n", "\n")

target = """            data = path.read_text(encoding="utf-8")
            if get_secret_redactor().redact_text(data) != data:
                raise ValueError("Secret material found in verification workspace")"""

replacement = """            data = path.read_text(encoding="utf-8")
            redactor = get_secret_redactor()
            check_fn = getattr(redactor, "has_secret_material", lambda t: redactor.redact_text(t) != t)
            if check_fn(data):
                raise ValueError("Secret material found in verification workspace")"""

if target in normalized:
    new_content = normalized.replace(target, replacement, 1)
    if "\r\n" in content:
        new_content = new_content.replace("\n", "\r\n")
    path.write_text(new_content, encoding="utf-8")
    print("SUCCESS")
else:
    print("TARGET NOT FOUND")

