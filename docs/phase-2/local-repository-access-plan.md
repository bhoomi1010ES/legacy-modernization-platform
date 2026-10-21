# Rebase — Phase 2 Architecture & Implementation Plan: Secure Browser-Based Local Repository Access

## 1. Overview & Objective

This document defines the architecture, security controls, lifecycle model, and implementation specifications for **browser-based local repository access** in the Rebase Multi-Agent Legacy Code Modernization Platform.

The objective is to enable authorized operators to select an existing project folder from their local computer directly via the web browser, run three-tier technology characterization, and initiate modernization jobs **without copying the codebase into Rebase's own repository directory** and **without assuming the backend has access to the user's local filesystem**.

---

## 2. Seven Core Architectural Requirements & Resolutions

### Requirement 1: Single-Upload Lifecycle via Staged Preview Snapshot Reuse
- **Problem**: Requiring the user to upload their entire repository twice (once for preview detection and once for job intake) wastes network bandwidth and introduces unacceptable latency for large codebases.
- **Solution: Secure, Temporary, Expiring Preview Staging**:
  1. When the user selects a local folder and initiates detection, the browser packages eligible source files and manifests into an in-memory zip bundle and streams it to `POST /api/v1/jobs/detect-stack/local`.
  2. The backend generates a cryptographically random `snapshot_id = uuid.uuid4()` and materializes the bundle into an isolated staging directory: `backend/staging_snapshots/{snapshot_id}/`.
  3. The backend calculates the authoritative **Canonical Snapshot Fingerprint** (see Requirement 2), executes `RepositoryInventoryScanner.scan()`, and runs `StackDetector._analyze_inventory()`.
  4. The staging snapshot is bound to:
     - `snapshot_id`: UUID
     - `owner_user_id`: UUID of the authenticated operator
     - `canonical_fingerprint`: SHA-256 hex digest
     - `created_at`: UTC timestamp
     - `expires_at`: UTC timestamp with strict 30-minute Time-To-Live (TTL)
     - `file_count`: integer
     - `total_bytes`: integer
     - `is_complete`: boolean
  5. The detection response returns `DetectedStackResponse` containing `preview_snapshot_id` and `snapshot_fingerprint`.
  6. When the user creates the job and proceeds to intake (`POST /api/v1/jobs/{job_id}/intake`), the client supplies `preview_snapshot_id` and `snapshot_fingerprint`.
  7. **Atomic Promotion to Permanent Workspace**:
     - The backend verifies: (a) caller owns the snapshot or is ADMIN, (b) `now < expires_at`, and (c) stored fingerprint strictly matches `snapshot_fingerprint`.
     - The backend promotes the staged directory to `backend/repo_workspaces/job_{job_id}` via atomic rename / directory move.
     - The staging lease is closed, and zero second upload is required.
  8. **Graceful Fallback**: If the 30-minute lease expires or the user rescans after edits, the intake endpoint supports a direct snapshot upload (`POST /api/v1/jobs/{job_id}/intake/local`), re-verifying the fingerprint.

### Requirement 2: Deterministic Canonical Snapshot Fingerprinting
To replace Git commit pinning with an equivalent immutability guarantee:
- The authoritative fingerprint must be independent of client claims, filesystem timestamps, directory traversal order, or platform line endings.
- **Canonical Entry Specification**:
  For every eligible regular file:
  1. `rel_path`: Normalized POSIX relative path using forward slashes (`/`), without leading or trailing slashes (e.g., `src/services/auth.ts`).
  2. `size_bytes`: File size in bytes as an ASCII decimal string.
  3. `content_sha256`: Lowercase hexadecimal SHA-256 digest of the raw file content bytes.
- **Canonical Line Representation**:
  $$\text{entry\_bytes} = \text{rel\_path} \,\|\, \texttt{"\\0"} \,\|\, \text{size\_bytes} \,\|\, \texttt{"\\0"} \,\|\, \text{content\_sha256} \,\|\, \texttt{"\\n"}$$
- **Sorting & Hashing**:
  All entry byte strings are sorted in strict ascending lexicographical byte order by `rel_path`.
  The authoritative `snapshot_fingerprint` is the SHA-256 hex digest of the concatenated sorted entries:
  $$\text{snapshot\_fingerprint} = \text{SHA-256}\left(\sum_{i=1}^{N} \text{entry\_bytes}_i\right)$$
- The backend independently computes and verifies this fingerprint directly from the materialized files on disk.

### Requirement 3: Explicit Differentiation of Complete vs. Incomplete Scans
- Hitting any traversal, size, count, or depth boundary must never silently truncate results while claiming a 100% complete scan.
- When any boundary is breached:
  - `scan_status` is explicitly set to `"PARTIAL"` (or `"INCONCLUSIVE"` if zero source code could be parsed).
  - `is_fallback` is preserved according to empirical findings.
  - An entry is appended to `warnings` detailing the exact breach, for example:
    - `Traversal depth limit (10) reached at 'legacy/modules/deep/...'. Subdirectories skipped.`
    - `File count limit (15,000) reached. Traversal truncated.`
    - `File 'big_data.sql' exceeds maximum inspectable size (2 MB) and was skipped.`
    - `Total source payload exceeds budget ceiling (100 MB). Scan is partial.`
  - The UI highlights the `PARTIAL` status badge in warning amber with actionable remediation advice.

### Requirement 4: Upload Quotas, Storage Isolation, Auth, Retention & Concurrency
- **Authentication & RBAC**:
  - `POST /api/v1/jobs/detect-stack/local` requires an authenticated session (`Depends(get_current_user)`).
  - Anonymous local uploads are rejected (`HTTP 401 Unauthorized`).
- **Upload Quotas**:
  - Single file inspection ceiling: 2 MB for manifests, 64 KB for SQL DDL.
  - Maximum upload payload size: 100 MB.
  - Maximum file count per upload: 15,000 files.
  - Maximum path depth: 10 levels.
- **Path Traversal & ZipSlip Defense**:
  - Absolute paths, UNC paths (`\\server\share`), drive letters (`C:`), null bytes (`\0`), and path-climbing components (`..`, `.`) are rejected server-side.
  - Every extracted file is verified: `target_path.resolve().is_relative_to(workspace_root.resolve())`.
  - Symlinks in uploaded archives are strictly prohibited and rejected.
- **Concurrency & Rate Limiting**:
  - Per-user semaphore limits concurrent active staging uploads to at most 2 per user.
- **Storage Isolation & Retention**:
  - Staging snapshots reside strictly in `backend/staging_snapshots/{snapshot_id}/` (never inside `repo_workspaces/`).
  - Strict 30-minute expiration.
  - Automated garbage collection: `cleanup_stale_staging_snapshots(max_age_minutes=30)` executes on startup, on preview requests, and on intake.
  - On cancellation, exception, or validation failure during upload extraction, the directory is immediately purged with retry logic for Windows file locks.

### Requirement 5: Non-Regression & Schema Compatibility
- Existing schemas ([backend/app/schemas/jobs.py](file:///c:/Users/EI%203/Desktop/rebase/backend/app/schemas/jobs.py)) are extended with backward-compatible optional fields:
  - `JobCreateRequest`:
    - `source_type: Optional[str] = "git"` ("git" | "local")
    - `preview_snapshot_id: Optional[str] = None`
    - `snapshot_fingerprint: Optional[str] = None`
  - `JobIntakeRequest`:
    - `preview_snapshot_id: Optional[str] = None`
    - `snapshot_fingerprint: Optional[str] = None`
  - `DetectedStackResponse`:
    - `preview_snapshot_id: Optional[str] = None`
    - `snapshot_fingerprint: Optional[str] = None`
- All existing Git repository clone, branch resolution, commit pinning, and GitHub PAT workflows operate with 100% backward compatibility.
- Job state machine transitions (`CREATED -> INTAKE -> ANALYZING ...`) remain unchanged.

### Requirement 6: Browser Picker & Unsupported Browser Fallback
- **Primary Mechanism**: `window.showDirectoryPicker({ mode: 'read' })` (File System Access API). Supported on Chromium-based browsers (Chrome, Edge, Opera, Brave).
- **Secondary Fallback**: `<input type="file" webkitdirectory />`. Fully supported on Firefox, Safari, and mobile browsers.
- **Error & Cancellation Handling**:
  - `AbortError`: User closed file picker dialog. Silently handled with zero error popups.
  - `NotAllowedError`: User denied directory access permission. Actionable error message displayed with option to retry or switch to fallback.
  - Browser lacking `showDirectoryPicker`: Automatically activates the `<input type="file" webkitdirectory>` fallback with clear helper text.

### Requirement 7: Test Coverage Plan
- Comprehensive unit and integration test suite:
  1. `test_local_source_adapter.py`:
     - Path traversal attack vectors (`../../`, `..\`, absolute paths, null bytes).
     - Deterministic Merkle fingerprint calculation and verification.
     - Ephemeral staging workspace isolation and cleanup.
     - Snapshot reuse: seamless promotion from staging to `repo_workspaces/job_{job_id}` during intake.
     - Snapshot expiry (TTL enforcement).
     - Snapshot authorization (User A cannot intake User B's staged snapshot).
     - Fingerprint mismatch rejection during intake (tamper detection).
     - Incomplete scan diagnostics (file count and depth limit triggers).
     - Full parity verification between Git source detection and local source detection on test fixtures.
     - Regression tests for Git URL validation, GitHub PAT, and commit pinning.
  2. `localSourceScanner.test.ts`:
     - File exclusion rules (`node_modules`, `.git`, `.venv`, `.env*`, `*.pem`, `*.key`).
     - Limit enforcement (depth, count, per-file size).
     - Deterministic client fingerprint matching server fingerprint.
     - Browser API feature detection and fallback triggers.

---

## 3. End-to-End Data Flow Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User as Operator
    participant FE as CreateJob.tsx
    participant Scanner as localSourceScanner.ts
    participant Route as FastAPI (/jobs/detect-stack/local)
    participant Adapter as LocalSourceAdapter
    participant Detector as StackDetector
    participant Staging as Disk (staging_snapshots/{id})
    participant Permanent as Disk (repo_workspaces/job_{id})

    User->>FE: Selects "Local Project Folder" & Clicks "Select Local Folder"
    FE->>Scanner: window.showDirectoryPicker() OR webkitdirectory
    Scanner->>Scanner: Recursive traversal (filters .git, node_modules, secrets; enforces depth <= 10)
    Scanner-->>FE: Stream progress & eligible file inventory
    FE->>Scanner: Package bundle & compute client fingerprint
    FE->>Route: POST /jobs/detect-stack/local (Multipart: bundle + metadata)
    
    Route->>Adapter: stage_and_validate_upload(bundle, user_id)
    Adapter->>Staging: Extract safely (ZipSlip checks, depth/count validation)
    Adapter->>Adapter: Compute authoritative Canonical Snapshot Fingerprint
    Adapter->>Detector: Run InventoryScanner & Three-Tier Analyzer
    Detector-->>Route: Return DetectedStackResponse (tiers, confidence, snapshot_id, fingerprint)
    Route-->>FE: Return HTTP 200 OK
    FE->>User: Render Three-Tier Architecture cards & fingerprint badge

    User->>FE: Confirms tiers & clicks "Create Modernization Job"
    FE->>Route: POST /jobs (JobCreateRequest with preview_snapshot_id & snapshot_fingerprint)
    Route-->>FE: Returns JobDetailResponse (status: CREATED)
    
    FE->>Route: POST /jobs/{id}/intake (JobIntakeRequest with preview_snapshot_id)
    Route->>Adapter: promote_staging_to_workspace(snapshot_id, job_id, user_id, expected_fingerprint)
    Adapter->>Staging: Verify ownership, expiry (<30m), & fingerprint match
    Staging->>Permanent: Atomic rename / move staging -> repo_workspaces/job_{id}
    Route-->>FE: Return JobDetailResponse (status: INTAKE, workspace materialized)
    FE->>User: Navigates to Job Dashboard
```

---

## 4. Remaining Trade-Offs & Decisions

| Decision | Chosen Approach | Rationale & Trade-Off |
| :--- | :--- | :--- |
| **Preview Snapshot Retention** | Staged in `backend/staging_snapshots/` with 30-min TTL | **Trade-off**: Consumes temporary server disk space for up to 30 minutes. **Benefit**: Eliminates duplicate multi-megabyte uploads, delivering instantaneous job creation and intake. |
| **Fingerprint Delimiter** | Null byte (`\0`) between path, size, and hash | **Trade-off**: Binary format in hashing. **Benefit**: Completely immune to delimiter injection attacks (unlike colons or commas which can appear in filenames). |
| **Browser Compatibility** | `showDirectoryPicker` with `webkitdirectory` fallback | **Trade-off**: Fallback requires user to select files via traditional folder prompt. **Benefit**: 100% cross-browser coverage across Chrome, Edge, Firefox, Safari, and Brave. |
| **Strict Exclusion Policy** | Hardcoded exclusion of dependencies & secrets | **Trade-off**: Obscure custom build tools in skipped folders require manual tier customization. **Benefit**: Prevents gigabyte-scale uploads of `node_modules` or accidental credential leakage. |
