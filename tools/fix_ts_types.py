import pathlib

# 1. Patch domain.ts
p = pathlib.Path("frontend/src/types/domain.ts")
text = p.read_text(encoding="utf-8")

if "blocking_reason?: string;" not in text:
    target_gate = "verification_guide?: GateVerificationGuide;\n}"
    replacement_gate = "verification_guide?: GateVerificationGuide;\n  blocking_reason?: string;\n}"
    if target_gate not in text:
        target_gate = "verification_guide?: GateVerificationGuide;\r\n}"
        replacement_gate = "verification_guide?: GateVerificationGuide;\r\n  blocking_reason?: string;\r\n}"
    assert target_gate in text, "target_gate not found"
    text = text.replace(target_gate, replacement_gate, 1)

if "output_payload?: any;" not in text:
    target_run = "evidence_artifact_ids?: string[];\n}"
    replacement_run = "evidence_artifact_ids?: string[];\n  output_payload?: any;\n}"
    if target_run not in text:
        target_run = "evidence_artifact_ids?: string[];\r\n}"
        replacement_run = "evidence_artifact_ids?: string[];\r\n  output_payload?: any;\r\n}"
    assert target_run in text, "target_run not found"
    text = text.replace(target_run, replacement_run, 1)

p.write_text(text, encoding="utf-8")
print("Successfully patched domain.ts")


# 2. Patch GateReviewModal.tsx
p_grm = pathlib.Path("frontend/src/components/GateReviewModal.tsx")
grm_text = p_grm.read_text(encoding="utf-8")

old_artifact_check = """  const isStale = gate.status === 'INVALIDATED' || Boolean(gate.blocking_reason && gate.blocking_reason.toLowerCase().includes('stale'));
  const hasArtifactEvidence = Boolean(
    (gate.artifact_hashes && Object.keys(gate.artifact_hashes).length > 0) ||
    (gate.artifact_ids && gate.artifact_ids.length > 0)
  );"""

new_artifact_check = """  const isStale = gate.status === 'INVALIDATED' || Boolean(gate.blocking_reason && gate.blocking_reason.toLowerCase().includes('stale'));
  const hasArtifactEvidence = Boolean(
    gate.artifact ||
    gate.artifact_hash ||
    (gate.artifact_hashes && Object.keys(gate.artifact_hashes).length > 0)
  );"""

if old_artifact_check in grm_text:
    grm_text = grm_text.replace(old_artifact_check, new_artifact_check, 1)
else:
    old_crlf = old_artifact_check.replace("\n", "\r\n")
    new_crlf = new_artifact_check.replace("\n", "\r\n")
    assert old_crlf in grm_text, "old_artifact_check not found in GateReviewModal.tsx"
    grm_text = grm_text.replace(old_crlf, new_crlf, 1)

p_grm.write_text(grm_text, encoding="utf-8")
print("Successfully patched GateReviewModal.tsx")


# 3. Patch AgentExecution.tsx
p_ae = pathlib.Path("frontend/src/components/workspace/AgentExecution.tsx")
ae_text = p_ae.read_text(encoding="utf-8")

old_ae_patterns = [
    ("run.status === 'COMPLETED'", "run.status === 'Completed'"),
    ("legacyModelRun?.status === 'COMPLETED'", "legacyModelRun?.status === 'Completed'"),
    ("architectRun?.status === 'COMPLETED'", "architectRun?.status === 'Completed'"),
    ("blueprintRun?.status === 'COMPLETED'", "blueprintRun?.status === 'Completed'"),
    ("feasibilityRun?.status === 'COMPLETED'", "feasibilityRun?.status === 'Completed'"),
]

for old, new in old_ae_patterns:
    ae_text = ae_text.replace(old, new)

p_ae.write_text(ae_text, encoding="utf-8")
print("Successfully patched AgentExecution.tsx")

