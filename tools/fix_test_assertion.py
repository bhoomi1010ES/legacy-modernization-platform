from pathlib import Path

test_file = Path("backend/tests/test_w02_isolation_and_ci.py")
content = test_file.read_text(encoding="utf-8")
content = content.replace('assert "styles.css" in static_app["styles.css"]', 'assert "font-family" in static_app["styles.css"]')
test_file.write_text(content, encoding="utf-8")
print("Fixed styles.css assertion.")

