from app.services.sandbox_protocol import validate_check_profile, approved_command

checks = [
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
system_checks = checks + [{"category": "schema", "command": ["python", "-m", "pytest", "-k", "schema", "-q", "-p", "no:cacheprovider"]}]

print("checks valid?:", validate_check_profile(checks, system=False))
print("system_checks valid?:", validate_check_profile(system_checks, system=True, schema_required=True))

