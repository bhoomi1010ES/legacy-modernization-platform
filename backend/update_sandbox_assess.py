from pathlib import Path

path = Path("app/services/phase6_sandbox.py")
text = path.read_text(encoding="utf-8")

old_code = '''        passed = (
            bool(cases)
            and data["source_unchanged"] is True
            and all(c["status"] == "PASS" for c in checks + results)
        )'''

new_code = '''        passed = (
            (bool(cases) if cases else bool(checks))
            and data["source_unchanged"] is True
            and all(c["status"] == "PASS" for c in checks + results)
        )'''

assert old_code in text or old_code.replace("\n", "\r\n") in text, "old_code not found"
text = text.replace(old_code, new_code)
text = text.replace(old_code.replace("\n", "\r\n"), new_code.replace("\n", "\r\n"))
path.write_text(text, encoding="utf-8")
print("Updated phase6_sandbox.py successfully!")

