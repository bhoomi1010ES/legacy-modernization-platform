from pathlib import Path

target_file = Path("frontend/src/components/GateReviewModal.tsx")
content = target_file.read_text(encoding="utf-8")

old_part = """const FALLBACK_VERIFICATION_GUIDES: Record<string, GateVerificationGuide> = {
  G1: {
    producing_agent: 'IntakeAgent & LegacyAnalyzerCoordinator',
    producing_agent_role: 'Legacy Repository Intake & AST Analyzer',
    work_summary:
      'Completed secure repository intake into an air-gapped rootless sandbox. Parsed the full legacy AST, extracted entities, HTTP route handlers, and dependency trees. Evaluated modern target compatibility against TypeScript / NestJS (Node.js 22 LTS) and generated an actionable capability gap matrix.',
    key_deliverables: [
      'Repository Inventory & AST Model',
      'Legacy Entity & Route Graph',
      'Target TypeScript / NestJS Blueprint',
      'Feasibility Scorecard & Gap Analysis',
    ],
    metrics: [
      { label: 'Capabilities Analyzed', value: '67 items', subtext: '100% evaluated', badge: 'ANALYZED' },
      { label: 'Feasibility Score', value: '100%', subtext: 'Zero critical blockers', badge: 'FEASIBLE' },
      { label: 'Target Runtime', value: 'Node.js 22 LTS', subtext: 'TypeScript 5.x / NestJS' },
      { label: 'Critical Blockers', value: '0 detected', subtext: 'Clean transition', badge: 'CLEAN' },
    ],
    checklist: [
      {
        id: 'g1_chk_1',
        title: 'Target Framework Parity',
        description: 'Verify that all detected legacy patterns (controllers, services, ORM entities) have direct equivalents in TypeScript / NestJS.',
      },
      {
        id: 'g1_chk_2',
        title: 'Capability Gap Resolutions',
        description: 'Confirm the selected adapter/custom resolution strategy for third-party libraries and specialized integrations.',
      },
      {
        id: 'g1_chk_3',
        title: 'Data Model & Schema Parity',
        description: 'Review database entity mapping to ensure zero data loss and valid relational foreign key constraints in the target ORM.',
      },
      {
        id: 'g1_chk_4',
        title: 'Modernization Scope & Budget',
        description: 'Ensure estimated modernization scope and token velocity limits are within the allocated project budget.',
      },
    ],
    next_agent: 'CharacterizerAgent',
    next_agent_role: 'Behavioral Replay Harness Specialist',
    next_agent_preview:
      'CharacterizerAgent will deploy the legacy system inside an air-gapped rootless container to record golden HTTP test vectors and state transitions.',
  },
  G2: {
    producing_agent: 'CharacterizerAgent',
    producing_agent_role: 'Behavioral Replay Harness Specialist',
    work_summary:
      'Deployed legacy application inside an isolated rootless container sandbox. Executed synthetic traffic and recorded golden HTTP request/response payloads, headers, status codes, and database state transitions to establish an immutable behavioral baseline.',
    key_deliverables: [
      'Frozen Characterization Test Suite',
      '42 Golden Fixture Vectors',
      'Zero-Tolerance Baseline Lock',
      'Database State Snapshot Fixtures',
    ],
    metrics: [
      { label: 'Test Vectors', value: '42 frozen tests', subtext: 'Golden fixtures', badge: 'FROZEN' },
      { label: 'Route Coverage', value: '100%', subtext: 'Legacy API surface', badge: 'COVERED' },
      { label: 'Baseline Lock', value: 'SHA-256', subtext: 'Cryptographic baseline' },
      { label: 'Side Effect Invariants', value: 'Captured', subtext: 'DB & HTTP contracts' },
    ],
    checklist: [
      {
        id: 'g2_chk_1',
        title: 'Critical Path Coverage',
        description: 'Verify that all revenue-critical and security-sensitive legacy endpoints have recorded test vectors.',
      },
      {
        id: 'g2_chk_2',
        title: 'Edge Cases & Error Handling',
        description: 'Ensure test vectors include validation failures, 4xx/5xx boundaries, and transaction rollbacks.',
      },
      {
        id: 'g2_chk_3',
        title: 'Secret & PII Sanitization',
        description: 'Confirm test fixtures contain sanitized mock data with zero production credentials or secrets.',
      },
      {
        id: 'g2_chk_4',
        title: 'Baseline Freeze Agreement',
        description: 'Confirm agreement that this test suite will serve as the non-negotiable ground truth for converted code.',
      },
    ],
    next_agent: 'PlannerCoordinator & ModulePlanner',
    next_agent_role: 'Architectural Decomposition & Dependency Wave Planner',
    next_agent_preview:
      'PlannerCoordinator will analyze the legacy model and target blueprint to decompose the codebase into modular packages, compute topological wave ordering, and verify DAG cyclicity.',
  },
  G3: {
    producing_agent: 'PlannerCoordinator & ModulePlanner',
    producing_agent_role: 'Architectural Decomposition & Dependency Wave Planner',
    work_summary:
      'Decomposed the legacy monolith into 14 decoupled modular components. Formulated 42 granular conversion tasks with explicit acceptance criteria and test contracts. Constructed a topological Directed Acyclic Graph (DAG) and scheduled 3 sequential conversion waves.',
    key_deliverables: [
      'Modular Conversion Plan',
      'Topological Wave DAG (3 Waves)',
      '42 Task Acceptance Specifications',
      'Zero-Cycle Dependency Matrix',
    ],
    metrics: [
      { label: 'Planned Modules', value: '14 modules', subtext: 'Decoupled domain packages', badge: 'MODULAR' },
      { label: 'Atomic Tasks', value: '42 tasks', subtext: 'With test contracts', badge: 'SPECIFIED' },
      { label: 'Execution Waves', value: '3 waves', subtext: 'Topologically ordered' },
      { label: 'Estimated Effort', value: '98.0 hours', subtext: 'Within budget ceiling' },
      { label: 'DAG Cycles', value: '0 cycles', subtext: 'Topologically valid', badge: 'CYCLE-FREE' },
    ],
    checklist: [
      {
        id: 'g3_chk_1',
        title: 'Wave 1 Zero-Dependency Isolation',
        description: 'Confirm Wave 1 modules (base types, database schema, utility helpers) have zero upstream dependencies.',
      },
      {
        id: 'g3_chk_2',
        title: 'Task Granularity & Acceptance Criteria',
        description: 'Ensure each of the 42 tasks specifies clear input contracts, output types, and test assertions.',
      },
      {
        id: 'g3_chk_3',
        title: 'Database Migration Sequencing',
        description: 'Validate that database entity migrations precede dependent domain services.',
      },
      {
        id: 'g3_chk_4',
        title: 'Effort & Budget Limits',
        description: 'Confirm the 98-hour conversion scope and projected token consumption fit within the allocated job budget.',
      },
    ],
    next_agent: 'CodeWriter Specialist Agents',
    next_agent_role: 'Rootless Container Code Conversion & Test Repair Specialist',
    next_agent_preview:
      'Specialist CodeWriter agents will be spawned into rootless container sandboxes to begin converting modules wave-by-wave, executing compiler validation and local test suites after every task.',
  },
  G4: {
    producing_agent: 'VerifierAgent & DualHarnessExecutor',
    producing_agent_role: 'Dual-Harness Replay & Parity Verification Specialist',
    work_summary:
      'Compiled converted TypeScript/NestJS codebase in rootless gVisor sandbox. Executed dual-harness replay comparing legacy vs modern outputs against identical test fixtures with zero unintended regressions detected.',
    key_deliverables: [
      'Dual-Harness Equivalence Report',
      'Intended Difference Catalog (4 Waivers)',
      '100% Strict Type Audit',
      'Cryptographic Parity Proof',
    ],
    metrics: [
      { label: 'Dual Replay Pass', value: '100%', subtext: 'All fixtures identical', badge: 'PASSED' },
      { label: 'Unintended Regressions', value: '0', subtext: 'Zero regression drift', badge: 'ZERO DRIFT' },
      { label: 'Approved Intentional Diffs', value: '4 waivers', subtext: 'ISO-8601 timestamps' },
      { label: 'Type Safety', value: '100% strict', subtext: 'Zero linter warnings' },
    ],"""

new_part = """const FALLBACK_VERIFICATION_GUIDES: Record<string, GateVerificationGuide> = {
  G1: {
    producing_agent: 'IntakeAgent & LegacyAnalyzerCoordinator',
    producing_agent_role: 'Legacy Repository Intake & AST Analyzer',
    work_summary:
      'Completed secure repository intake into an air-gapped rootless sandbox. Parsed the legacy AST, extracted entities, route handlers, and dependency trees. Evaluated compatibility against the target blueprint and generated an actionable capability gap matrix.',
    key_deliverables: [
      'Repository Inventory & AST Model',
      'Legacy Entity & Route Graph',
      'Target Architecture Blueprint',
      'Feasibility Scorecard & Gap Analysis',
    ],
    metrics: [
      { label: 'Capabilities Analyzed', value: 'Evaluated', subtext: '100% assessed', badge: 'ANALYZED' },
      { label: 'Feasibility Score', value: '100%', subtext: 'Zero critical blockers', badge: 'FEASIBLE' },
      { label: 'Target Runtime', value: 'Target Framework', subtext: 'Idiomatic patterns' },
      { label: 'Critical Blockers', value: '0 detected', subtext: 'Clean transition', badge: 'CLEAN' },
    ],
    checklist: [
      {
        id: 'g1_chk_1',
        title: 'Target Framework Parity',
        description: 'Verify that all detected legacy patterns (controllers, services, ORM entities) have direct equivalents in the target stack.',
      },
      {
        id: 'g1_chk_2',
        title: 'Capability Gap Resolutions',
        description: 'Confirm the selected adapter/custom resolution strategy for third-party libraries and specialized integrations.',
      },
      {
        id: 'g1_chk_3',
        title: 'Data Model & Schema Parity',
        description: 'Review database entity mapping to ensure zero data loss and valid relational foreign key constraints in the target ORM.',
      },
      {
        id: 'g1_chk_4',
        title: 'Modernization Scope & Budget',
        description: 'Ensure estimated modernization scope and token velocity limits are within the allocated project budget.',
      },
    ],
    next_agent: 'CharacterizerAgent',
    next_agent_role: 'Behavioral Replay Harness Specialist',
    next_agent_preview:
      'CharacterizerAgent will deploy the legacy system inside an air-gapped rootless container to record golden HTTP test vectors and state transitions.',
  },
  G2: {
    producing_agent: 'CharacterizerAgent',
    producing_agent_role: 'Behavioral Replay Harness Specialist',
    work_summary:
      'Deployed legacy application inside an isolated rootless container sandbox. Executed synthetic traffic and recorded golden HTTP request/response payloads, headers, status codes, and database state transitions to establish an immutable behavioral baseline.',
    key_deliverables: [
      'Frozen Characterization Test Suite',
      'Golden Fixture Vectors',
      'Zero-Tolerance Baseline Lock',
      'Database State Snapshot Fixtures',
    ],
    metrics: [
      { label: 'Test Vectors', value: 'Recorded', subtext: 'Golden fixtures', badge: 'FROZEN' },
      { label: 'Route Coverage', value: '100%', subtext: 'Legacy API surface', badge: 'COVERED' },
      { label: 'Baseline Lock', value: 'SHA-256', subtext: 'Cryptographic baseline' },
      { label: 'Side Effect Invariants', value: 'Captured', subtext: 'DB & HTTP contracts' },
    ],
    checklist: [
      {
        id: 'g2_chk_1',
        title: 'Critical Path Coverage',
        description: 'Verify that all revenue-critical and security-sensitive legacy endpoints have recorded test vectors.',
      },
      {
        id: 'g2_chk_2',
        title: 'Edge Cases & Error Handling',
        description: 'Ensure test vectors include validation failures, 4xx/5xx boundaries, and transaction rollbacks.',
      },
      {
        id: 'g2_chk_3',
        title: 'Secret & PII Sanitization',
        description: 'Confirm test fixtures contain sanitized mock data with zero production credentials or secrets.',
      },
      {
        id: 'g2_chk_4',
        title: 'Baseline Freeze Agreement',
        description: 'Confirm agreement that this test suite will serve as the non-negotiable ground truth for converted code.',
      },
    ],
    next_agent: 'PlannerCoordinator & ModulePlanner',
    next_agent_role: 'Architectural Decomposition & Dependency Wave Planner',
    next_agent_preview:
      'PlannerCoordinator will analyze the legacy model and target blueprint to decompose the codebase into modular packages, compute topological wave ordering, and verify DAG cyclicity.',
  },
  G3: {
    producing_agent: 'PlannerCoordinator & ModulePlanner',
    producing_agent_role: 'Architectural Decomposition & Dependency Wave Planner',
    work_summary:
      'Decomposed the legacy codebase into decoupled modular components. Formulated granular conversion tasks with explicit acceptance criteria and test contracts. Constructed a topological Directed Acyclic Graph (DAG) and scheduled sequential conversion waves.',
    key_deliverables: [
      'Modular Conversion Plan',
      'Topological Wave DAG',
      'Task Acceptance Specifications',
      'Zero-Cycle Dependency Matrix',
    ],
    metrics: [
      { label: 'Planned Modules', value: 'Decomposed', subtext: 'Domain packages', badge: 'MODULAR' },
      { label: 'Atomic Tasks', value: 'Specified', subtext: 'With test contracts', badge: 'SPECIFIED' },
      { label: 'Execution Waves', value: 'Scheduled', subtext: 'Topologically ordered' },
      { label: 'Estimated Effort', value: 'Budgeted', subtext: 'Within budget ceiling' },
      { label: 'DAG Cycles', value: '0 cycles', subtext: 'Topologically valid', badge: 'CYCLE-FREE' },
    ],
    checklist: [
      {
        id: 'g3_chk_1',
        title: 'Wave 1 Zero-Dependency Isolation',
        description: 'Confirm Wave 1 modules (base types, database schema, utility helpers) have zero upstream dependencies.',
      },
      {
        id: 'g3_chk_2',
        title: 'Task Granularity & Acceptance Criteria',
        description: 'Ensure each conversion task specifies clear input contracts, output types, and test assertions.',
      },
      {
        id: 'g3_chk_3',
        title: 'Database Migration Sequencing',
        description: 'Validate that database entity migrations precede dependent domain services.',
      },
      {
        id: 'g3_chk_4',
        title: 'Effort & Budget Limits',
        description: 'Confirm the conversion scope and projected token consumption fit within the allocated job budget.',
      },
    ],
    next_agent: 'CodeWriter Specialist Agents',
    next_agent_role: 'Rootless Container Code Conversion & Test Repair Specialist',
    next_agent_preview:
      'Specialist CodeWriter agents will be spawned into rootless container sandboxes to begin converting modules wave-by-wave, executing compiler validation and local test suites after every task.',
  },
  G4: {
    producing_agent: 'VerifierAgent & DualHarnessExecutor',
    producing_agent_role: 'Dual-Harness Replay & Parity Verification Specialist',
    work_summary:
      'Compiled converted codebase in rootless gVisor sandbox. Executed dual-harness replay comparing legacy vs modern outputs against identical test fixtures with zero unintended regressions detected.',
    key_deliverables: [
      'Dual-Harness Equivalence Report',
      'Intended Difference Catalog',
      'Strict Type & Contract Audit',
      'Cryptographic Parity Proof',
    ],
    metrics: [
      { label: 'Dual Replay Pass', value: 'Verified', subtext: 'All fixtures identical', badge: 'PASSED' },
      { label: 'Unintended Regressions', value: '0', subtext: 'Zero regression drift', badge: 'ZERO DRIFT' },
      { label: 'Approved Intentional Diffs', value: 'Documented', subtext: 'Audited waivers' },
      { label: 'Type Safety', value: 'Strict', subtext: 'Zero linter warnings' },
    ],"""

if old_part in content:
    content = content.replace(old_part, new_part)
    target_file.write_text(content, encoding="utf-8")
    print("Replaced static hardcoded fallbacks in GateReviewModal.tsx")
else:
    print("Warning: old_part not found in GateReviewModal.tsx")

