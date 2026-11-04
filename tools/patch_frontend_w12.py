"""Patch frontend files for W12: UI-01, UI-03, UI-04."""

import pathlib

# 1. Patch JobDetail.tsx (UI-03)
job_detail_path = pathlib.Path("frontend/src/pages/JobDetail.tsx")
jd_text = job_detail_path.read_text(encoding="utf-8")

old_jd_text = """            <h2 style={{ fontSize: '16px', fontWeight: 650, marginBottom: '10px' }}>Dual-Harness Behavioral Verification (Gate G4)</h2>
            <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', marginBottom: '20px' }}>
              Both legacy and converted services executed against identical fixtures. Zero unintended regressions detected.
            </p>"""

new_jd_text = """            <h2 style={{ fontSize: '16px', fontWeight: 650, marginBottom: '10px' }}>Dual-Harness Behavioral Verification (Gate G4)</h2>
            <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', marginBottom: '20px' }}>
              {job?.status === 'COMPLETED'
                ? 'Both legacy and converted services executed against identical fixtures. Behavioral parity verified.'
                : 'Verification pending or unobserved. No verified equivalence claims can be made until dual-harness execution completes.'}
            </p>"""

assert old_jd_text in jd_text, "old_jd_text not found in JobDetail.tsx"
jd_text = jd_text.replace(old_jd_text, new_jd_text, 1)
job_detail_path.write_text(jd_text, encoding="utf-8")
print("Successfully patched JobDetail.tsx (UI-03)")


# 2. Patch GateDetailExplanationView.tsx (UI-04)
gdev_path = pathlib.Path("frontend/src/components/GateDetailExplanationView.tsx")
gdev_text = gdev_path.read_text(encoding="utf-8")

# Replace G3 hardcoded fallbacks
old_g3 = """    total_modules: conversionPlan?.modules?.length ?? 14,
    total_tasks: conversionPlan?.estimates?.tasks_count ?? conversionPlan?.tasks?.length ?? 42,
    waves_count: conversionPlan?.waves?.length ?? 3,
    estimated_hours: conversionPlan?.estimates?.total_hours ?? 98.0,"""

new_g3 = """    total_modules: conversionPlan?.modules?.length ?? 0,
    total_tasks: conversionPlan?.estimates?.tasks_count ?? conversionPlan?.tasks?.length ?? 0,
    waves_count: conversionPlan?.waves?.length ?? 0,
    estimated_hours: conversionPlan?.estimates?.total_hours ?? 0.0,"""

assert old_g3 in gdev_text, "old_g3 not found in GateDetailExplanationView.tsx"
gdev_text = gdev_text.replace(old_g3, new_g3, 1)

old_g3_card = """    card3Value = '3 Waves · 14 Modules';
    card4Label = 'Deliverable Status';
    card4Value = 'ConversionPlan v1';
    specialistHeader = 'Specialist Wave Planning & Gate G3 Recommendation:';
    specialistBody = `Topological dependency DAG validated with 0 cyclic dependencies. 14 decoupled modular domain packages scheduled across 3 sequential waves. Granular test contracts and compiler assertions attached to all 42 conversion tasks.`;"""

new_g3_card = """    card3Value = conversionPlan ? `${conversionPlan.waves?.length || 0} Waves · ${conversionPlan.modules?.length || 0} Modules` : 'Awaiting Plan Generation';
    card4Label = 'Deliverable Status';
    card4Value = conversionPlan ? 'ConversionPlan v1' : 'EVIDENCE_UNAVAILABLE';
    specialistHeader = 'Specialist Wave Planning & Gate G3 Recommendation:';
    specialistBody = conversionPlan
      ? `Topological dependency DAG validated with 0 cyclic dependencies. ${conversionPlan.modules?.length || 0} decoupled modular domain packages scheduled across ${conversionPlan.waves?.length || 0} waves.`
      : 'EVIDENCE_UNAVAILABLE: Conversion plan deliverable evidence is missing or has not yet been computed.';"""

assert old_g3_card in gdev_text, "old_g3_card not found in GateDetailExplanationView.tsx"
gdev_text = gdev_text.replace(old_g3_card, new_g3_card, 1)

# Replace G4 hardcoded fallbacks
old_g4 = """    parity_rate: 1.0,
    unintended_regressions: 0,
    approved_intentional_differences: 4,
    strict_typing_score: 1.0,"""

new_g4 = """    parity_rate: job?.status === 'COMPLETED' ? 1.0 : 0.0,
    unintended_regressions: 0,
    approved_intentional_differences: 0,
    strict_typing_score: job?.status === 'COMPLETED' ? 1.0 : 0.0,"""

assert old_g4 in gdev_text, "old_g4 not found in GateDetailExplanationView.tsx"
gdev_text = gdev_text.replace(old_g4, new_g4, 1)

old_g4_card = """    card3Value = '100% Parity (0 Drift)';
    card4Label = 'Deliverable Status';
    card4Value = 'EquivalenceReport v1';
    specialistHeader = 'Specialist Dual-Harness Verification & Gate G4 Recommendation:';
    specialistBody = `Dual-harness replay completed across all golden characterization test fixtures. Zero unintended regressions or schema drifts detected. Approved intentional differences verified and cataloged for release sign-off.`;"""

new_g4_card = """    card3Value = job?.status === 'COMPLETED' ? '100% Parity (0 Drift)' : 'Awaiting Verification';
    card4Label = 'Deliverable Status';
    card4Value = job?.status === 'COMPLETED' ? 'EquivalenceReport v1' : 'EVIDENCE_UNAVAILABLE';
    specialistHeader = 'Specialist Dual-Harness Verification & Gate G4 Recommendation:';
    specialistBody = job?.status === 'COMPLETED'
      ? 'Dual-harness replay completed across all golden characterization test fixtures. Zero unintended regressions or schema drifts detected.'
      : 'EVIDENCE_UNAVAILABLE: Final equivalence report evidence has not yet been verified or loaded.';"""

assert old_g4_card in gdev_text, "old_g4_card not found in GateDetailExplanationView.tsx"
gdev_text = gdev_text.replace(old_g4_card, new_g4_card, 1)

old_g4_matrix = """        target: '42 / 42 Fixtures Matched (100%)',"""
new_g4_matrix = """        target: job?.status === 'COMPLETED' ? 'All Fixtures Matched (100%)' : 'Verification Incomplete',"""

assert old_g4_matrix in gdev_text, "old_g4_matrix not found in GateDetailExplanationView.tsx"
gdev_text = gdev_text.replace(old_g4_matrix, new_g4_matrix, 1)

gdev_path.write_text(gdev_text, encoding="utf-8")
print("Successfully patched GateDetailExplanationView.tsx (UI-04)")


# 3. Patch GateReviewModal.tsx (UI-04)
grm_path = pathlib.Path("frontend/src/components/GateReviewModal.tsx")
grm_text = grm_path.read_text(encoding="utf-8")

old_grm_desc = """        id: 'g4_chk_2',
        title: 'Inspect & Sign Difference Waivers',
        description: 'Review the 4 intentional differences (e.g. ISO-8601 datetime strings, empty array return) and sign approval waivers.',"""

new_grm_desc = """        id: 'g4_chk_2',
        title: 'Inspect & Sign Difference Waivers',
        description: 'Review intentional differences (e.g. ISO-8601 datetime strings, empty array return) and sign approval waivers.',"""

assert old_grm_desc in grm_text, "old_grm_desc not found in GateReviewModal.tsx"
grm_text = grm_text.replace(old_grm_desc, new_grm_desc, 1)

# Update blockers logic to check stale evidence and missing artifacts
old_blockers = """  const g2Blockers: string[] = [];
  if (gate.gate_type === 'G2') {
    if (charReport) {
      if (charReport.schema_status === 'REVIEW_REQUIRED') {
        g2Blockers.push('Schema migration plan requires manual review before G2 approval.');
      }
      if (charReport.schema_status !== 'NOT_APPLICABLE' && charReport.schema_validation_status && charReport.schema_validation_status !== 'PASS') {
        g2Blockers.push('Schema plan must be validated with disposable sample data before G2 approval.');
      }
      const nonPassing = (charReport.cases || []).filter(c => c.outcome !== 'PASSED');
      if (nonPassing.length > 0) {
        const unavail = nonPassing.filter(c => c.outcome === 'UNAVAILABLE').length;
        const failed = nonPassing.filter(c => c.outcome === 'FAILED').length;
        g2Blockers.push(`${nonPassing.length} scenario(s) not passing (${unavail} UNAVAILABLE, ${failed} FAILED; all must be PASSED).`);
      }
      if (charReport.g2_readiness?.blocking_reasons?.length) {
        g2Blockers.push(...charReport.g2_readiness.blocking_reasons);
      }
    } else {
      g2Blockers.push('Loading characterization suite evidence...');
    }
  }"""

new_blockers = """  const isStale = gate.status === 'INVALIDATED' || Boolean(gate.blocking_reason && gate.blocking_reason.toLowerCase().includes('stale'));
  const hasArtifactEvidence = Boolean(
    (gate.artifact_hashes && Object.keys(gate.artifact_hashes).length > 0) ||
    (gate.artifact_ids && gate.artifact_ids.length > 0)
  );

  const g2Blockers: string[] = [];
  if (isStale) {
    g2Blockers.push('Gate evidence is STALE because upstream dependencies have drifted. Re-verification required.');
  }
  if (!hasArtifactEvidence && gate.status === 'PENDING') {
    g2Blockers.push('EVIDENCE_UNAVAILABLE: Gate cannot be approved because required deliverable evidence is missing.');
  }

  if (gate.gate_type === 'G2') {
    if (charReport) {
      if (charReport.schema_status === 'REVIEW_REQUIRED') {
        g2Blockers.push('Schema migration plan requires manual review before G2 approval.');
      }
      if (charReport.schema_status !== 'NOT_APPLICABLE' && charReport.schema_validation_status && charReport.schema_validation_status !== 'PASS') {
        g2Blockers.push('Schema plan must be validated with disposable sample data before G2 approval.');
      }
      const nonPassing = (charReport.cases || []).filter(c => c.outcome !== 'PASSED');
      if (nonPassing.length > 0) {
        const unavail = nonPassing.filter(c => c.outcome === 'UNAVAILABLE').length;
        const failed = nonPassing.filter(c => c.outcome === 'FAILED').length;
        g2Blockers.push(`${nonPassing.length} scenario(s) not passing (${unavail} UNAVAILABLE, ${failed} FAILED; all must be PASSED).`);
      }
      if (charReport.g2_readiness?.blocking_reasons?.length) {
        g2Blockers.push(...charReport.g2_readiness.blocking_reasons);
      }
    } else {
      g2Blockers.push('Loading characterization suite evidence...');
    }
  }"""

assert old_blockers in grm_text, "old_blockers not found in GateReviewModal.tsx"
grm_text = grm_text.replace(old_blockers, new_blockers, 1)

# Update approval button check
old_btn = """            {gate.gate_type === 'G2' && g2Blockers.length > 0 && (
              <div role="alert" style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--destructive)', borderRadius: '6px', padding: '12px', marginBottom: '16px' }}>
                <strong style={{ color: 'var(--destructive)', display: 'block', fontSize: '12px', marginBottom: '4px' }}>
                  G2 Approval Blocked (Unmet Invariant Prerequisites):
                </strong>
                <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '11px', color: 'var(--foreground)' }}>
                  {g2Blockers.map((b, idx) => (
                    <li key={idx} style={{ marginBottom: '2px' }}>{b}</li>
                  ))}
                </ul>
              </div>
            )}"""

new_btn = """            {g2Blockers.length > 0 && (
              <div role="alert" style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--destructive)', borderRadius: '6px', padding: '12px', marginBottom: '16px' }}>
                <strong style={{ color: 'var(--destructive)', display: 'block', fontSize: '12px', marginBottom: '4px' }}>
                  Approval Blocked (Unmet Invariant Prerequisites):
                </strong>
                <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '11px', color: 'var(--foreground)' }}>
                  {g2Blockers.map((b, idx) => (
                    <li key={idx} style={{ marginBottom: '2px' }}>{b}</li>
                  ))}
                </ul>
              </div>
            )}"""

assert old_btn in grm_text, "old_btn not found in GateReviewModal.tsx"
grm_text = grm_text.replace(old_btn, new_btn, 1)

old_approve = """              <button
                className="button button-primary"
                onClick={() => handleDecision('APPROVED')}
                disabled={loading || (gate.gate_type === 'G2' && g2Blockers.length > 0)}
                title={gate.gate_type === 'G2' && g2Blockers.length > 0 ? g2Blockers[0] : undefined}
              >"""

new_approve = """              <button
                className="button button-primary"
                onClick={() => handleDecision('APPROVED')}
                disabled={loading || g2Blockers.length > 0}
                title={g2Blockers.length > 0 ? g2Blockers[0] : undefined}
              >"""

assert old_approve in grm_text, "old_approve not found in GateReviewModal.tsx"
grm_text = grm_text.replace(old_approve, new_approve, 1)

grm_path.write_text(grm_text, encoding="utf-8")
print("Successfully patched GateReviewModal.tsx (UI-04)")


# 4. Patch AgentExecution.tsx (UI-01)
ae_path = pathlib.Path("frontend/src/components/workspace/AgentExecution.tsx")
ae_text = ae_path.read_text(encoding="utf-8")

old_workers = """    const specializedWorkers: SpecializedWorker[] = [
      {
        name: 'Structure Worker',
        type: 'structure',
        status: isAnalysisRunning ? 'Running' : analysisStatus === 'FAILED' ? 'Failed' : analysisStatus === 'COMPLETED' ? 'Completed' : 'Pending',
        summary: 'Parsed repository directory layout and module boundary definitions.',
      },
      {
        name: 'Dependency Worker',
        type: 'dependency',
        status: isAnalysisRunning ? 'Running' : analysisStatus === 'FAILED' ? 'Failed' : analysisStatus === 'COMPLETED' ? 'Completed' : 'Pending',
        summary: 'Resolved direct and transitive dependencies from project manifests.',
      },
      {
        name: 'Interface Worker',
        type: 'interface',
        status: isAnalysisRunning ? 'Running' : analysisStatus === 'FAILED' ? 'Failed' : analysisStatus === 'COMPLETED' ? 'Completed' : 'Pending',
        summary: 'Identified public HTTP routes, controller endpoints, and RPC stubs.',
      },
      {
        name: 'Data Worker',
        type: 'data',
        status: analysisStatus === 'FAILED' ? 'Failed' : analysisStatus === 'COMPLETED' ? 'Completed' : isAnalysisRunning ? 'Running' : 'Pending',
        summary: 'Inspected database models, migrations, ORM schemas, and queries.',
      },
      {
        name: 'Test Worker',
        type: 'test',
        status: analysisStatus === 'FAILED' ? 'Failed' : analysisStatus === 'COMPLETED' ? 'Completed' : isAnalysisRunning ? 'Running' : 'Pending',
        summary: 'Cataloged unit/integration test suites and mock boundaries.',
      },
      {
        name: 'Integration Worker',
        type: 'integration',
        status: analysisStatus === 'COMPLETED' ? 'Completed' : 'Pending',
        summary: 'Verified external service contracts and messaging brokers.',
      },
      {
        name: 'Risk Worker',
        type: 'risk',
        status: analysisStatus === 'COMPLETED' ? 'Completed' : 'Pending',
        summary: 'Analyzed security risks, sensitive data surfaces, and migration hazards.',
      },
    ];

    // Stage 3: Legacy Model
    const legacyModelStatus =
      analysisStatus !== 'COMPLETED'
        ? 'PENDING'
        : 'COMPLETED';

    // Stage 4: Architect
    const architectStatus =
      legacyModelStatus !== 'COMPLETED'
        ? 'PENDING'
        : 'COMPLETED';

    // Stage 5: Target Blueprint
    const blueprintStatus =
      architectStatus !== 'COMPLETED'
        ? 'PENDING'
        : 'COMPLETED';

    // Stage 6: Feasibility Agent
    const feasibilityStatus =
      blueprintStatus !== 'COMPLETED'
        ? 'PENDING'
        : 'COMPLETED';"""

new_workers = """    const workerRunMap: Record<string, AgentRun | undefined> = {
      structure: latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('structure')),
      dependency: latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('dependency')),
      interface: latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('interface')),
      data: latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('data')),
      test: latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('test')),
      integration: latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('integration')),
      risk: latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('risk')),
    };

    const getWorkerStatus = (type: string): 'Pending' | 'Running' | 'Completed' | 'Failed' => {
      const run = workerRunMap[type];
      if (!run) {
        return isAnalysisRunning ? 'Running' : 'Pending';
      }
      if (run.status === 'SUCCEEDED' || run.status === 'COMPLETED') return 'Completed';
      if (run.status === 'FAILED' || run.status === 'BLOCKED') return 'Failed';
      if (run.status === 'RUNNING' || run.status === 'QUEUED') return 'Running';
      return 'Pending';
    };

    const getWorkerSummary = (type: string, fallbackDesc: string): string => {
      const run = workerRunMap[type];
      if (!run) {
        return isAnalysisRunning ? 'Worker dispatched for analysis...' : 'Awaiting worker execution.';
      }
      if (run.status === 'SUCCEEDED' || run.status === 'COMPLETED') {
        return run.output_payload?.summary || fallbackDesc;
      }
      if (run.error_message) return run.error_message;
      return fallbackDesc;
    };

    const specializedWorkers: SpecializedWorker[] = [
      {
        name: 'Structure Worker',
        type: 'structure',
        status: getWorkerStatus('structure'),
        summary: getWorkerSummary('structure', 'Parsed repository directory layout and module boundary definitions.'),
      },
      {
        name: 'Dependency Worker',
        type: 'dependency',
        status: getWorkerStatus('dependency'),
        summary: getWorkerSummary('dependency', 'Resolved direct and transitive dependencies from project manifests.'),
      },
      {
        name: 'Interface Worker',
        type: 'interface',
        status: getWorkerStatus('interface'),
        summary: getWorkerSummary('interface', 'Identified public HTTP routes, controller endpoints, and RPC stubs.'),
      },
      {
        name: 'Data Worker',
        type: 'data',
        status: getWorkerStatus('data'),
        summary: getWorkerSummary('data', 'Inspected database models, migrations, ORM schemas, and queries.'),
      },
      {
        name: 'Test Worker',
        type: 'test',
        status: getWorkerStatus('test'),
        summary: getWorkerSummary('test', 'Cataloged unit/integration test suites and mock boundaries.'),
      },
      {
        name: 'Integration Worker',
        type: 'integration',
        status: getWorkerStatus('integration'),
        summary: getWorkerSummary('integration', 'Verified external service contracts and messaging brokers.'),
      },
      {
        name: 'Risk Worker',
        type: 'risk',
        status: getWorkerStatus('risk'),
        summary: getWorkerSummary('risk', 'Analyzed security risks, sensitive data surfaces, and migration hazards.'),
      },
    ];

    // Stage 3: Legacy Model
    const legacyModelRun = latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('legacy_model') || r.agent_name.toLowerCase().includes('legacymodel'));
    const legacyModelStatus = legacyModelRun?.status === 'SUCCEEDED' || legacyModelRun?.status === 'COMPLETED'
      ? 'COMPLETED'
      : legacyModelRun?.status === 'RUNNING'
      ? 'RUNNING'
      : (analysisStatus === 'COMPLETED' && isPlanning)
      ? 'COMPLETED'
      : 'PENDING';

    // Stage 4: Architect
    const architectRun = latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('architect'));
    const architectStatus = architectRun?.status === 'SUCCEEDED' || architectRun?.status === 'COMPLETED'
      ? 'COMPLETED'
      : architectRun?.status === 'RUNNING'
      ? 'RUNNING'
      : architectRun?.status === 'FAILED'
      ? 'FAILED'
      : (legacyModelStatus === 'COMPLETED' && isPlanning)
      ? 'COMPLETED'
      : 'PENDING';

    // Stage 5: Target Blueprint
    const blueprintRun = latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('blueprint'));
    const blueprintStatus = blueprintRun?.status === 'SUCCEEDED' || blueprintRun?.status === 'COMPLETED'
      ? 'COMPLETED'
      : blueprintRun?.status === 'RUNNING'
      ? 'RUNNING'
      : (architectStatus === 'COMPLETED' && isPlanning)
      ? 'COMPLETED'
      : 'PENDING';

    // Stage 6: Feasibility Agent
    const feasibilityRun = latestRunsByAgent.find(r => r.agent_name.toLowerCase().includes('feasibility'));
    const feasibilityStatus = feasibilityRun?.status === 'SUCCEEDED' || feasibilityRun?.status === 'COMPLETED'
      ? 'COMPLETED'
      : feasibilityRun?.status === 'RUNNING'
      ? 'RUNNING'
      : feasibilityRun?.status === 'FAILED'
      ? 'FAILED'
      : (blueprintStatus === 'COMPLETED' && isPlanning)
      ? 'COMPLETED'
      : 'PENDING';"""

assert old_workers in ae_text, "old_workers not found in AgentExecution.tsx"
ae_text = ae_text.replace(old_workers, new_workers, 1)

ae_path.write_text(ae_text, encoding="utf-8")
print("Successfully patched AgentExecution.tsx (UI-01)")

