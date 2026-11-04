from pathlib import Path

path = Path("tools/test_full_bootstrap_flow.py")
content = path.read_text(encoding="utf-8")
content = content.replace("https://localhost:8443/repo.git", "https://github.com/example/sample-repo.git")
path.write_text(content, encoding="utf-8")
print("Updated repo url in test_full_bootstrap_flow.py")

