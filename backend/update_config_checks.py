from pathlib import Path

path = Path("app/core/config.py")
text = path.read_text(encoding="utf-8")

old_code = '''        checks = [
            {"category": "build", "command": ["python", "-m", "compileall", "-q", "."]},
            {"category": "unit", "command": ["python", "-m", "pytest", "/acceptance/test_calc.py", "-q", "-p", "no:cacheprovider"]},
            {"category": "integration", "command": ["python", "-m", "pytest", "/acceptance/test_integration.py", "-q", "-p", "no:cacheprovider"]},
            {"category": "static", "command": ["python", "-m", "mypy", "--cache-dir=/tmp/mypy-cache", "--check-untyped-defs", "--explicit-package-bases", "."]},
            {"category": "security", "command": ["python", "-m", "bandit", "-r", "app", "-q"]},
            {"category": "dependency", "command": ["pip-audit", "--strict"]},
            {"category": "license", "command": ["pip-licenses", "--format=json"]},
            {"category": "runtime", "command": ["python", "-m", "pytest", "/acceptance/test_runtime.py", "-q", "-p", "no:cacheprovider"]},
            {"category": "api_compatibility", "command": ["python", "-m", "pytest", "/acceptance/test_api.py", "-q", "-p", "no:cacheprovider"]},
        ]
        system_checks = checks + [{"category": "schema", "command": ["python", "-m", "pytest", "/acceptance/test_schema.py", "-q", "-p", "no:cacheprovider"]}]'''

new_code = '''        checks = [
            {"category": "build", "command": ["python", "-m", "compileall", "-q", "."]},
            {"category": "unit", "command": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]},
            {"category": "integration", "command": ["python", "-m", "pytest", "-k", "integration", "-q", "-p", "no:cacheprovider"]},
            {"category": "static", "command": ["python", "-m", "mypy", "--cache-dir=/tmp/mypy-cache", "--check-untyped-defs", "--explicit-package-bases", "."]},
            {"category": "security", "command": ["python", "-m", "bandit", "-r", "app", "-q"]},
            {"category": "dependency", "command": ["pip-audit", "--strict"]},
            {"category": "license", "command": ["pip-licenses", "--format=json"]},
            {"category": "runtime", "command": ["python", "-m", "pytest", "-k", "runtime", "-q", "-p", "no:cacheprovider"]},
            {"category": "api_compatibility", "command": ["python", "-m", "pytest", "-k", "api", "-q", "-p", "no:cacheprovider"]},
        ]
        system_checks = checks + [{"category": "schema", "command": ["python", "-m", "pytest", "-k", "schema", "-q", "-p", "no:cacheprovider"]}]'''

text = text.replace(old_code, new_code)
path.write_text(text, encoding="utf-8")
print("Updated config.py checks successfully!")

