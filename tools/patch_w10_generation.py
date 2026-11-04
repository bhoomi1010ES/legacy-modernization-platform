with open("backend/tests/test_w10_independent_verifier.py", "r", encoding="utf-8") as f:
    c = f.read()

# Add generation to imports
c = c.replace(
    "from tests.test_phase6 import (\n    ready,\n",
    "from tests.test_phase6 import (\n    ready,\n    generation,\n",
    1
)

# 1. Update test_verifier_separate_durable_work_item_and_lease
old_gate_1 = """    from app.services.model_gateway import FakeModelProvider, build_fake_gateway
    gateway = build_fake_gateway(FakeModelProvider([
        json.dumps({
            "files": {"modern/calc.py": "def add(x: int, y: int) -> int:\\n    return x + y\\n"},
            "design_notes": "Clean addition implementation",
            "assumptions": [],
            "test_commands": [],
        })
    ]))"""

new_gate_1 = """    from app.services.model_gateway import FakeModelProvider, build_fake_gateway
    gateway = build_fake_gateway(FakeModelProvider([generation(3)]))"""

assert old_gate_1 in c, "old_gate_1 not found"
c = c.replace(old_gate_1, new_gate_1, 1)

# 2. Update test_repair_creates_new_attempt_with_target_failed_tests
old_gate_2 = """    gateway = build_fake_gateway(FakeModelProvider([
        json.dumps({
            "files": {"modern/calc.py": "def add(x, y):\\n    return x + y + 1\\n"},
            "design_notes": "Intentional bug for repair test",
            "assumptions": [],
            "test_commands": [],
        }),
        # Second attempt fixes the bug
        json.dumps({
            "files": {"modern/calc.py": "def add(x, y):\\n    return x + y\\n"},
            "design_notes": "Repaired code",
            "assumptions": [],
            "test_commands": [],
        }),
    ]))"""

new_gate_2 = """    gateway = build_fake_gateway(FakeModelProvider([generation(4), generation(3)]))"""

assert old_gate_2 in c, "old_gate_2 not found"
c = c.replace(old_gate_2, new_gate_2, 1)

# 3. Update test_repeated_failure_exhaustion_escalates_to_waiting_for_human
old_gate_3 = """    gateway = build_fake_gateway(FakeModelProvider([
        json.dumps({
            "files": {"modern/calc.py": "def add(x, y):\\n    return 999\\n"},
            "design_notes": "Buggy",
            "assumptions": [],
            "test_commands": [],
        }),
        json.dumps({
            "files": {"modern/calc.py": "def add(x, y):\\n    return 999\\n"},
            "design_notes": "Still buggy",
            "assumptions": [],
            "test_commands": [],
        }),
    ]))"""

new_gate_3 = """    gateway = build_fake_gateway(FakeModelProvider([generation(4), generation(4)]))"""

assert old_gate_3 in c, "old_gate_3 not found"
c = c.replace(old_gate_3, new_gate_3, 1)

with open("backend/tests/test_w10_independent_verifier.py", "w", encoding="utf-8") as f:
    f.write(c)

print("Updated test_w10_independent_verifier.py with generation helper")

