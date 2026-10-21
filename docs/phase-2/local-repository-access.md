# Rebase — Secure Browser-Based Local Repository Access Guide

## Overview

This guide documents the architecture, lifecycle, security boundaries, and operational practices for **browser-based local repository access** in the Rebase Multi-Agent Legacy Code Modernization Platform.

Rebase allows operators to select and modernize codebases residing on their local machine without copying projects into Rebase's own directory, and without assuming the remote backend has direct filesystem access to the client computer.

---

## 1. Direct Local PC Path Pasting & Ingestion Model

Rebase supports direct local directory inspection and intake for operators running on their machine:

### A. Direct PC Path Pasting (Primary Mode)
When the operator selects the **Local Project Folder** tab:
- The UI presents a clean path input field (`Local Project Location (Folder Path on your PC)`).
- The user simply types or pastes their local directory path (e.g. `C:\Users\EI 3\Desktop\my-legacy-app` or `/home/user/projects/legacy-app`).
- Clicking **Inspect Path / Detect Stack** (or pressing Enter) sends the path to `POST /api/v1/jobs/detect-stack` with `source_type="local"`.
- The backend resolves the directory directly on disk, computes the authoritative canonical Merkle fingerprint, and runs static technology stack characterization in milliseconds—**with zero file upload, zero browser packaging, and zero network overhead**.
- During job intake, the backend copies the project files directly from disk into `backend/repo_workspaces/job_{job_id}` while filtering vendor and cache directories.

### B. Browser Ingestion & Remote Fallback
For browser-based sessions without direct backend filesystem access:
- Rebase supports ephemeral staged bundles (`LocalSourceScanner` and `LocalSourceAdapter`) via `POST /api/v1/jobs/detect-stack/local`.
- ZipSlip defense, symlink rejection, and 30-minute staging leases ensure complete isolation.

---

## 2. Security Boundaries & Zero-Trust Defense

Rebase enforces multiple concentric security controls to safeguard client code and server infrastructure:

### A. Client-Side Filtering (Before Upload)
Before any bytes leave the browser, `LocalSourceScanner`:
1. **Excludes Vendor & Build Directories**: `.git`, `node_modules`, `.venv`, `venv`, `dist`, `build`, `target`, `vendor`, `__pycache__`, etc.
2. **Excludes Sensitive Credentials & Keys**: `.env*`, `*.pem`, `*.key`, `id_rsa*`, `*.pfx`, `*.keystore`, `*.credentials`, `secrets.json`.
3. **Enforces Ceilings**:
   - Traversal depth limit: $\le 10$ levels.
   - File count limit: $\le 15{,}000$ files.
   - Inspectable file size: $\le 2\,\text{MB}$ per file.
   - Total preview bundle size: $\le 50\,\text{MB}$.
4. **Cancellation**: Operators can cancel in-flight directory scans instantly via `AbortController`.

### B. Server-Side Path Traversal & ZipSlip Defense
The FastAPI backend (`LocalSourceAdapter`) treats all uploaded filenames as untrusted user input:
1. **ZipSlip Defense**: Every archive member path is strictly validated:
   - Rejects leading slashes (`/`, `\\`), drive letters (`C:`), null bytes (`\0`), and path climbing (`..`).
   - Asserts: `target_path.resolve().is_relative_to(staging_dir.resolve())`.
2. **Symlink Prohibition**: Archives containing symlink headers are rejected immediately.
3. **Resource Caps**: Enforces 100 MB total uncompressed size ceiling and 10 MB per-file ceiling.

---

## 3. Canonical Merkle Snapshot Fingerprinting

To guarantee code immutability matching Git commit pinning (`resolved_commit`), Rebase calculates an authoritative **Canonical Snapshot Fingerprint**:

### Formula & Encoding
For each eligible regular file:
1. `rel_path`: Normalized POSIX relative path (forward slashes `/`, no leading slash).
2. `size_bytes`: File size in bytes as an ASCII decimal string.
3. `content_sha256`: Hexadecimal SHA-256 digest of raw file content bytes.

Each entry is formatted with unambiguous null-byte delimiters:
$$\text{entry} = \text{rel\_path} \,\|\, \texttt{"\\0"} \,\|\, \text{size\_bytes} \,\|\, \texttt{"\\0"} \,\|\, \text{content\_sha256} \,\|\, \texttt{"\\n"}$$

All entries are sorted in strict ascending lexicographical byte order by `rel_path`. The snapshot fingerprint is:
$$\text{snapshot\_fingerprint} = \text{SHA-256}\left(\sum_{i=1}^{N} \text{entry}_i\right)$$

The backend computes this fingerprint independently on disk. Any file modification between preview and intake produces a fingerprint mismatch and raises `HTTP 409 Conflict`.

---

## 4. Single-Upload Lifecycle & Staging Lease

To eliminate duplicate multi-megabyte uploads, Rebase implements a **30-Minute Staged Preview Lease**:

```
[ User Selects Folder ]
          │
          ▼
[ Browser Scanner: Filters .git/secrets, builds ZIP ]
          │
          ▼  POST /api/v1/jobs/detect-stack/local
[ Staged in backend/staging_snapshots/{snapshot_id}/ ]
          │  - Tagged with owner_user_id & 30m TTL
          │  - Authoritative Canonical Fingerprint generated
          ▼
[ Three-Tier Detection Response with preview_snapshot_id ]
          │
          ▼  (User configures tiers & creates job)
[ Job Created (Status: CREATED) ]
          │
          ▼  POST /api/v1/jobs/{job_id}/intake (with preview_snapshot_id)
[ Atomic Promotion: staging_snapshots/{id} -> repo_workspaces/job_{job_id} ]
          │  - Zero second upload required
          │  - Ownership verified, TTL checked, fingerprint validated
          ▼
[ Job Intake Complete (Status: INTAKE) ]
```

### Stale Snapshot Garbage Collection
A background cleanup routine (`cleanup_stale_staging_snapshots`) automatically purges any staging directories whose 30-minute lease has expired. If a user returns after 30 minutes, the fallback endpoint (`POST /api/v1/jobs/{job_id}/intake/local`) enables direct snapshot intake without friction.

---

## 5. Completeness vs. Partial Scans

When local repository bounds are breached (e.g. depth limit, file count limit, or total size ceiling):
- Rebase **never silently truncates** files while reporting a false 100% complete scan.
- The scan status is set to **`PARTIAL`** (or `INCONCLUSIVE`).
- The `warnings` array details every breached limit and skipped file.
- The UI renders amber alert banners displaying exact boundary diagnostics.
