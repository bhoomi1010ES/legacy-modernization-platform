export interface EvidenceArtifact<T> {
  artifact_id: string;
  version: number;
  content_hash: string;
  download_url: string | null;
  content: T;
}

export interface JobReport {
  job_id: string;
  run_id: string;
  status: string;
  source_stack: string;
  target_stack: string;
  source_commit: string;
  integrated_commit: string | null;
  branch: string;
  baseline_hash: string;
  plan_hash: string;
  modules: Array<{ module_id: string; name: string; status: string; attempt_id: string; branch: string; commit: string; changed_files: string[]; diff: string }>;
  counts: { total: number; executed: number; passed: number; failed: number; unobserved: number };
  coverage: { percent?: number; untested_paths?: string[]; limitations?: string[]; known_legacy_bugs?: string[]; normalization?: unknown[] };
  findings: Array<{ finding_id: string; severity: string; message: string; evidence_ref: string }>;
  waivers: unknown[];
  decisions: unknown[];
  costs: Record<string, unknown>;
  duration_ms: number;
  limitations: string[];
  evidence: {
    integration: { artifact_id: string; hash: string; conflicts?: string[]; diff?: string; merge_history?: unknown[] };
    verification: { artifact_id: string; hash: string; image_id?: string; container_name?: string; reason?: string; checks?: Array<{ category: string; command: string[]; exit_code: number | null; duration_ms: number; status: string; stdout?: string; stderr?: string }> };
    sbom: { artifact_id: string; hash: string; status: string; tool?: string; tool_version?: string; format?: string };
  };
}

export interface FinalDelivery {
  job_id: string;
  job_status: string;
  delivery_ready: boolean;
  package_current?: boolean;
  production_cutover_included: false;
  report: EvidenceArtifact<JobReport> | null;
  gate: { gate_id: string; status: string; version: number; artifact_hashes: Record<string, string> } | null;
  pull_request: { status: string; url?: string | null; branch?: string; commit?: string; instructions?: string[]; reason?: string; summary?: string };
  delivery_record: EvidenceArtifact<{ delivered_at: string; commit: string; rationale: string }> | null;
  limitations: string[];
  allowed_actions: string[];
}
