path = r"backend/app/services/supervisor_graph.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

target = 'return {"execution_verdict": "SUCCESS", "events": [{"type": "ANALYSIS_SUCCESS"}]}            elif agent_name in ("ARCHITECT", "ArchitectAgent"):'
rep = 'return {"execution_verdict": "SUCCESS", "events": [{"type": "ANALYSIS_SUCCESS"}]}\n\n            elif agent_name in ("ARCHITECT", "ArchitectAgent"):'

assert target in c, "target not found"
c = c.replace(target, rep, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Fixed syntax in supervisor_graph.py")

