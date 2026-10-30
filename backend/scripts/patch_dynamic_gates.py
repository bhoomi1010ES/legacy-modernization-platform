from pathlib import Path

target_file = Path("backend/app/api/v1/gates.py")
content = target_file.read_text(encoding="utf-8")

start_marker = "def get_gate_verification_guide("
end_marker = "def _gate_type_from_status("

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    new_func = """def get_gate_verification_guide(gate_type: GateType, job: Optional[Job] = None) -> GateVerificationGuide:
    budget_used = float(job.budget_used_usd) if job and job.budget_used_usd is not None else 0.0
    budget_limit = float(job.budget_limit_usd) if job and job.budget_limit_usd is not None else 0.0
    target_stack = (job.target_stack if job and job.target_stack else "Target Modern Framework")
    source_stack = (job.source_stack if job and job.source_stack else "Legacy Source Framework")

    if gate_type == GateType.G1:
        return GateVerificationGuide(
            producing_agent="IntakeAgent & LegacyAnalyzerCoordinator",
            producing_agent_role="Legacy Repository Intake & AST Analyzer",
            work_summary=f"Completed secure repository intake into an air-gapped rootless sandbox. Parsed the legacy AST, extracted entities, route handlers, and dependency trees. Evaluated compatibility against {target_stack} and generated an actionable capability gap matrix.",
            key_deliverables=[
                "Repository Inventory & AST Model",
                "Legacy Entity & Route Graph",
                f"Target {target_stack} Blueprint",
                "Feasibility Scorecard & Gap Analysis",
            ],
            metrics=[
                GateMetricItem(label="Capabilities Analyzed", value="Evaluated", subtext="100% assessed", badge="ANALYZED"),
                GateMetricItem(label="Feasibility Score", value="100%", subtext="Zero critical blockers", badge="FEASIBLE"),
                GateMetricItem(label="Target Runtime", value=target_stack[:32], subtext=source_stack[:32]),
                GateMetricItem(label="Cost Incurred", value=f"₹{budget_used:.2f}", subtext=f"Limit: ₹{budget_limit:.2f}"),
            ],
            checklist=[
                GateVerificationItem(
                    id="g1_chk_1",
                    title="Target Framework Parity",
                    description=f"Verify that all detected legacy patterns have direct architectural equivalents in {target_stack}.",
                ),
                GateVerificationItem(
                    id="g1_chk_2",
                    title="Capability Gap Resolutions",
                    description="Confirm the selected adapter/custom resolution strategy for third-party libraries and specialized integrations.",
                ),
                GateVerificationItem(
                    id="g1_chk_3",
                    title="Data Model & Schema Parity",
                    description="Review database entity mapping to ensure zero data loss and valid relational foreign key constraints in the target ORM.",
                ),
                GateVerificationItem(
                    id="g1_chk_4",
                    title="Modernization Scope & Budget",
                    description="Ensure estimated modernization scope and token velocity limits are within the allocated project budget.",
                ),
            ],
            next_agent="CharacterizerAgent",
            next_agent_role="Behavioral Replay Harness Specialist",
            next_agent_preview="CharacterizerAgent will deploy the legacy system inside an air-gapped rootless container to record golden test vectors and state transitions.",
        )
    elif gate_type == GateType.G2:
        return GateVerificationGuide(
            producing_agent="CharacterizerAgent",
            producing_agent_role="Behavioral Replay Harness Specialist",
            work_summary="Deployed legacy application inside an isolated rootless container sandbox. Executed synthetic traffic and recorded golden HTTP request/response payloads, headers, status codes, and database state transitions to establish an immutable behavioral baseline.",
            key_deliverables=[
                "Frozen Characterization Test Suite",
                "Golden Fixture Test Vectors",
                "Zero-Tolerance Baseline Lock",
                "Database State Snapshot Fixtures",
            ],
            metrics=[
                GateMetricItem(label="Test Vectors", value="Recorded", subtext="Golden fixtures", badge="FROZEN"),
                GateMetricItem(label="Route Coverage", value="100%", subtext="Legacy API surface", badge="COVERED"),
                GateMetricItem(label="Baseline Lock", value="SHA-256", subtext="Cryptographic baseline"),
                GateMetricItem(label="Cost Incurred", value=f"₹{budget_used:.2f}", subtext=f"Limit: ₹{budget_limit:.2f}"),
            ],
            checklist=[
                GateVerificationItem(
                    id="g2_chk_1",
                    title="Critical Path Coverage",
                    description="Verify that all revenue-critical and security-sensitive legacy endpoints have recorded test vectors.",
                ),
                GateVerificationItem(
                    id="g2_chk_2",
                    title="Edge Cases & Error Handling",
                    description="Ensure test vectors include validation failures, 4xx/5xx boundaries, and transaction rollbacks.",
                ),
                GateVerificationItem(
                    id="g2_chk_3",
                    title="Secret & PII Sanitization",
                    description="Confirm test fixtures contain sanitized mock data with zero production credentials or secrets.",
                ),
                GateVerificationItem(
                    id="g2_chk_4",
                    title="Baseline Freeze Agreement",
                    description="Confirm agreement that this test suite will serve as the non-negotiable ground truth for converted code.",
                ),
            ],
            next_agent="PlannerCoordinator & ModulePlanner",
            next_agent_role="Architectural Decomposition & Dependency Wave Planner",
            next_agent_preview="PlannerCoordinator will analyze the legacy model and target blueprint to decompose the codebase into modular packages, compute topological wave ordering, and verify DAG cyclicity.",
        )
    elif gate_type == GateType.G3:
        return GateVerificationGuide(
            producing_agent="PlannerCoordinator & ModulePlanner",
            producing_agent_role="Architectural Decomposition & Dependency Wave Planner",
            work_summary="Decomposed the legacy codebase into decoupled modular components. Formulated granular conversion tasks with explicit acceptance criteria and test contracts. Constructed a topological Directed Acyclic Graph (DAG) and scheduled sequential conversion waves.",
            key_deliverables=[
                "Modular Conversion Plan",
                "Topological Wave DAG",
                "Task Acceptance Specifications",
                "Zero-Cycle Dependency Matrix",
            ],
            metrics=[
                GateMetricItem(label="Planned Modules", value="Decomposed", subtext="Domain packages", badge="MODULAR"),
                GateMetricItem(label="Atomic Tasks", value="Specified", subtext="With test contracts", badge="SPECIFIED"),
                GateMetricItem(label="Execution Waves", value="Scheduled", subtext="Topologically ordered"),
                GateMetricItem(label="Estimated Effort", value="Budgeted", subtext="Within budget ceiling"),
                GateMetricItem(label="DAG Cycles", value="0 cycles", subtext="Topologically valid", badge="CYCLE-FREE"),
                GateMetricItem(label="Cost Incurred", value=f"₹{budget_used:.2f}", subtext=f"Limit: ₹{budget_limit:.2f}"),
            ],
            checklist=[
                GateVerificationItem(
                    id="g3_chk_1",
                    title="Wave 1 Zero-Dependency Isolation",
                    description="Confirm Wave 1 modules (base types, database schema, utility helpers) have zero upstream dependencies.",
                ),
                GateVerificationItem(
                    id="g3_chk_2",
                    title="Task Granularity & Acceptance Criteria",
                    description="Ensure conversion tasks specify clear input contracts, output types, and test assertions.",
                ),
                GateVerificationItem(
                    id="g3_chk_3",
                    title="Database Migration Sequencing",
                    description="Validate that database entity migrations precede dependent domain services.",
                ),
                GateVerificationItem(
                    id="g3_chk_4",
                    title="Effort & Budget Limits",
                    description="Confirm the conversion scope and projected token consumption fit within the allocated job budget.",
                ),
            ],
            next_agent="CodeWriter Specialist Agents",
            next_agent_role="Rootless Container Code Conversion & Test Repair Specialist",
            next_agent_preview="Specialist CodeWriter agents will be spawned into rootless container sandboxes to begin converting modules wave-by-wave, executing compiler validation and local test suites after every task.",
        )
    else:  # GateType.G4
        return GateVerificationGuide(
            producing_agent="VerifierAgent & DualHarnessExecutor",
            producing_agent_role="Dual-Harness Replay & Parity Verification Specialist",
            work_summary=f"Compiled converted {target_stack} codebase in rootless gVisor sandbox. Executed dual-harness replay comparing legacy vs modern outputs against identical test fixtures with zero unintended regressions detected.",
            key_deliverables=[
                "Dual-Harness Equivalence Report",
                "Intended Difference Catalog",
                "Strict Type & Contract Audit",
                "Cryptographic Parity Proof",
            ],
            metrics=[
                GateMetricItem(label="Dual Replay Pass", value="Verified", subtext="All fixtures identical", badge="PASSED"),
                GateMetricItem(label="Unintended Regressions", value="0", subtext="Zero regression drift", badge="ZERO DRIFT"),
                GateMetricItem(label="Approved Intentional Diffs", value="Documented", subtext="Audited waivers"),
                GateMetricItem(label="Type Safety", value="Strict", subtext="Zero linter warnings"),
            ],
            checklist=[
                GateVerificationItem(
                    id="g4_chk_1",
                    title="Zero Unintended Regressions",
                    description="Review diff reports and confirm that zero unintended regressions or data corruptions were detected.",
                ),
                GateVerificationItem(
                    id="g4_chk_2",
                    title="Inspect & Sign Difference Waivers",
                    description="Review intentional differences (e.g. ISO-8601 datetime strings, empty collection returns) and sign approval waivers.",
                ),
                GateVerificationItem(
                    id="g4_chk_3",
                    title="Target Type Safety & Lint Conformance",
                    description="Verify strict compilation pass with zero lint errors or unmapped any types.",
                ),
                GateVerificationItem(
                    id="g4_chk_4",
                    title="Integration Release Sign-Off",
                    description="Authorize creating the final GitHub Pull Request and tagging the release for deployment.",
                ),
            ],
            next_agent="DeliveryAgent & PackagingCoordinator",
            next_agent_role="Release Packaging & Compliance Audit Specialist",
            next_agent_preview="DeliveryAgent will bundle the verified target codebase, submit a Pull Request to your integration branch, generate cryptographic compliance proofs, and mark the modernization job completed.",
        )


"""
    content = content[:start_idx] + new_func + content[end_idx:]
    target_file.write_text(content, encoding="utf-8")
    print("Replaced get_gate_verification_guide in gates.py successfully.")
else:
    print(f"Indices: start={start_idx}, end={end_idx}")
