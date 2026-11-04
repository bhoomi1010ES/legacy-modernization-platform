with open("backend/app/services/phase6_sandbox.py", "r", encoding="utf-8") as f:
    c = f.read()

target = "if settings.SANDBOX_RUNTIME not in {'docker-rootless','gvisor-rootless'}:"
rep = "if settings.SANDBOX_RUNTIME not in {'docker-rootless', 'gvisor-rootless', 'e2b-microvm'}:"
assert target in c, "Target not found"
c = c.replace(target, rep, 1)

with open("backend/app/services/phase6_sandbox.py", "w", encoding="utf-8") as f:
    f.write(c)

print("Updated phase6_sandbox.py")

# Also fix test_real_docker_acceptance_when_explicitly_configured in test_phase6.py
with open("backend/tests/test_phase6.py", "r", encoding="utf-8") as f:
    c2 = f.read()

target2 = """    if os.getenv("PHASE6_RUN_REAL_ACCEPTANCE") != "1":
        pytest.skip(
            "Real Docker/model/target adapter acceptance requires explicit configured fixture"
        )
    sandbox.configuration()"""

rep2 = """    if os.getenv("PHASE6_RUN_REAL_ACCEPTANCE") != "1":
        pytest.skip(
            "Real Docker/model/target adapter acceptance requires explicit configured fixture"
        )
    sandbox.configuration("python-fastapi")"""

if target2 in c2:
    c2 = c2.replace(target2, rep2, 1)
    with open("backend/tests/test_phase6.py", "w", encoding="utf-8") as f:
        f.write(c2)
    print("Updated test_phase6.py")

