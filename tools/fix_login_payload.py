from pathlib import Path

path = Path("tools/test_full_bootstrap_flow.py")
content = path.read_text(encoding="utf-8")
content = content.replace(
    'data={"username": reg_payload["email"], "password": reg_payload["password"]}',
    'json={"email": reg_payload["email"], "password": reg_payload["password"]}',
)
path.write_text(content, encoding="utf-8")
print("Fixed login json payload in test_full_bootstrap_flow.py")

