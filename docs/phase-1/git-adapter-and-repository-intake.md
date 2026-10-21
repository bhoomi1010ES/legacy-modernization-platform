# Controlled Git Adapter & Repository Intake Engine
## Phase 1 Source Intake, SSRF Defense and Sandbox Isolation

**Document:** `docs/phase-1/git-adapter-and-repository-intake.md`  
**Phase:** Phase 1 (Repository Intake & Git Infrastructure)  
**Date:** October 19, 2026  
**Status:** Completed & Verified  

---

## 1. Security Architecture & Threat Mitigations

Ingesting untrusted legacy source code poses severe security hazards including Server-Side Request Forgery (SSRF), arbitrary command injection via Git submodules, and automatic code execution through rogue hooks.

The **ControlledGitAdapter** implements defense-in-depth:

```text
Incoming Repo URL
       │
       ▼
[1. Character Sanitization] ──> Reject control chars (; & | ` $ \n)
       │
       ▼
[2. Protocol Allowlist]     ──> Allow ONLY https, git, ssh (file: test-only)
       │
       ▼
[3. DNS Pre-Resolution]     ──> Resolve host -> Block 127.0.0.0/8, 10.0.0.0/8,
       │                         172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16
       ▼
[4. Subprocess Execution]   ──> Safe vector: subprocess.run(["git", ...], shell=False)
       │                         Sanitized environment (no platform credentials)
       ▼
[5. Code Execution Isolation] ─> -c core.hooksPath=/dev/null (No hooks executed)
                                 -c protocol.ext.allow=never
                                 -c core.symlinks=false
```

---

## 2. Protected Branch Policy

To prevent rogue agent pushes or unintended modifications to the production repository, the adapter enforces a strict protected branch policy:

- **Protected Branches:** `main`, `master`, `production`, `release`, `develop`.
- **Policy Enforcement:** `verify_branch_is_not_protected(branch_name)` checks mutations against the protected set and raises `ConflictException` (409).
- **Safe Branch Naming Schema:** All modernization branches are strictly generated under:
  ```text
  job/{job_id}/{module_slug}
  ```
  Verified by regex: `^job/[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+$`

---

## 3. Supported Git Operations

1. **`clone_repository(job_id, repo_url, revision, depth=50)`**: Clones into an isolated workspace directory (`repo_workspaces/job_{job_id}`) and resolves the exact commit hash (`git rev-parse HEAD`).
2. **`create_module_branch(job_id, module_slug, base_branch)`**: Branches out safely for module-level conversion.
3. **`get_diff(job_id, base_ref, target_ref)`**: Generates unified diffs between conversion attempts and legacy baselines.
4. **`get_commit_metadata(job_id, revision)`**: Inspects author, commit timestamp, subject, and full hash.
5. **`cleanup_workspace(job_id)`**: Completely cleans workspace directories on Windows and POSIX systems with read-only permission recovery.
