from pathlib import Path

path = Path("tools/test_full_bootstrap_flow.py")
content = path.read_text(encoding="utf-8")
content = content.replace("user_data['role_id']", "user_data['role']")
path.write_text(content, encoding="utf-8")
print("Fixed print statement in test_full_bootstrap_flow.py")

