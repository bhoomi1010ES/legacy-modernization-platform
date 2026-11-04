path = r"backend/app/services/supervisor_service.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# 1. Update graph invocation to pass thread_id config
target1 = "            graph_task = asyncio.create_task(authoritative_supervisor_graph.ainvoke(initial_state))"
rep1 = """            graph_task = asyncio.create_task(
                authoritative_supervisor_graph.ainvoke(
                    initial_state,
                    config={"configurable": {"thread_id": str(job_id), "correlation_id": correlation_id}},
                )
            )"""

if target1 not in c:
    target1 = target1.replace("\n", "\r\n")
    rep1 = rep1.replace("\n", "\r\n")

assert target1 in c, "target1 not found in supervisor_service.py"
c = c.replace(target1, rep1, 1)

# 2. Add rationale length validation to recover_failed_phase6_job
target2 = """        if not {"G1", "G2", "G3"}.issubset(approved_types):
            raise ConflictException(f"Cannot recover Phase 6 job: missing approved gates (approved: {approved_types})")"""

rep2 = """        if not {"G1", "G2", "G3"}.issubset(approved_types):
            raise ConflictException(f"Cannot recover Phase 6 job: missing approved gates (approved: {approved_types})")

        if len(rationale.strip()) < 10:
            raise ConflictException("Diagnostic rationale must be at least 10 characters long.")"""

if target2 not in c:
    target2 = target2.replace("\n", "\r\n")
    rep2 = rep2.replace("\n", "\r\n")

assert target2 in c, "target2 not found in supervisor_service.py"
c = c.replace(target2, rep2, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Updated supervisor_service.py successfully")

