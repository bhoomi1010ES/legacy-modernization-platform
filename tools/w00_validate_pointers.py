import os
from pathlib import Path

ROOT = Path(r"c:\Users\lenovo\Desktop\rebase")

checks = [
    # SEC
    ("SEC-01", "backend/app/services/auth_service.py", ["master", "bypass", "dev", "password", "DEV_PASSWORDS"]),
    ("SEC-02", "backend/app/api/v1/auth.py", ["register", "REVIEWER", "role"]),
    ("SEC-03", "backend/app/api/v1/jobs.py", ["ADMIN", "membership", "owner_user_id"]),
    ("SEC-04", "backend/app/api/v1/jobs.py", ["detect-stack", "detect-stack/local"]),
    ("SEC-05", "backend/app/core/config.py", ["SESSION_COOKIE_SECURE", "SESSION_COOKIE_HTTPONLY"]),
    ("SEC-06", ".env", ["OPENAI_API_KEY", "SECRET_KEY"]),
    ("SEC-07", "backend/app/api/v1/artifacts.py", ["artifact:read", "post", "create_artifact"]),
    ("SEC-08", "backend/app/main.py", ["TrustedHostMiddleware", "CORSMiddleware"]),

    # FLOW
    ("FLOW-01", "backend/app/services/supervisor_router.py", ["ready_modules[0]", "ready_modules"]),
    ("FLOW-02", "backend/app/services/continuous_pipeline.py", ["ContinuousPipelineService", "deprecated"]),
    ("FLOW-03", "backend/app/services/supervisor_graph.py", ["handle_wait", "pause_for_human", "END"]),
    ("FLOW-04", "backend/app/services/phase4_orchestrator.py", ["AnalyzerCoordinator", "Phase4Orchestrator"]),
    ("FLOW-05", "backend/app/services/supervisor_graph.py", ["checkpointer", "compile"]),
    ("FLOW-06", "backend/app/services/supervisor_service.py", ["recover_failed_phase6_job", "CONVERTING"]),
    ("FLOW-07", "backend/app/services/supervisor_graph.py", ["unknown", "SUCCESS", "fallback"]),

    # DATA
    ("DATA-01", "backend/app/services/schema_data_agent.py", ["8400", "18.50", "Anthropic", "Claude"]),
    ("DATA-02", "backend/alembic.ini", ["script_location"]),
    ("DATA-03", "backend/app/services/artifact_service.py", ["put_object", "delete_object", "compensation"]),

    # TEST
    ("TEST-01", "backend/app/services/phase6_sandbox.py", ["actual.output", "expected.output", "static", "web"]),
    ("TEST-02", "backend/app/core/config.py", ["PHASE6_CHECK_COMMANDS_JSON", "compileall"]),
    ("TEST-03", "backend/app/services/feasibility_agent.py", ["TypeScript", "pytest", "READY"]),
    ("TEST-04", "backend/tests/conftest.py", ["AsyncSessionLocal", "ENVIRONMENT"]),

    # UI
    ("UI-01", "frontend/src/components/AgentExecution.tsx", ["stage", "COMPLETED"]),
    ("UI-02", "frontend/src/components/ActivityLog.tsx", ["initialEvents", "timeline"]),
    ("UI-03", "frontend/src/pages/JobDetail.tsx", ["regression", "verified"]),
    ("UI-04", "frontend/src/components/GateReviewModal.tsx", ["regression", "replay"]),
    ("UI-05", "backend/app/api/v1/jobs.py", ["_job_to_response", "progress", "modules_count"]),
]

results = []
for cid, rel_path, keywords in checks:
    fp = ROOT / rel_path
    if not fp.exists():
        results.append((cid, rel_path, "MISSING_FILE", []))
        continue
    try:
        content = fp.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        found_kw = {}
        for kw in keywords:
            matches = [i + 1 for i, line in enumerate(lines) if kw.lower() in line.lower()]
            found_kw[kw] = matches[:5]
        results.append((cid, rel_path, "EXISTS", found_kw))
    except Exception as e:
        results.append((cid, rel_path, f"ERROR: {e}", []))

for cid, path, status, kw_matches in results:
    print(f"[{cid}] {path} -> {status}")
    if isinstance(kw_matches, dict):
        for kw, lines in kw_matches.items():
            print(f"    '{kw}': lines {lines}")

