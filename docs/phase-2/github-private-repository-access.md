# Rebase — Secure GitHub Private Repository Access Using Fine-Grained PAT

## Overview

This guide documents the architecture, lifecycle, and operational practices for accessing private GitHub repositories in the Rebase Multi-Agent Legacy Code Modernization Platform using GitHub Fine-Grained Personal Access Tokens (PAT).

Rebase enables authorized operators to preview legacy application stacks and clone approved sources for autonomous modernization without storing credentials in persistent databases or exposing them in logs or URLs.

---

## 1. Creating a Fine-Grained GitHub PAT

GitHub fine-grained personal access tokens allow granular, repository-scoped permissions conforming to the principle of least privilege.

### Recommended Configuration

1. **Log in to GitHub**: Navigate to **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens**.
2. **Generate new token**: Click **Generate new token**.
3. **Token details**:
   - **Token name**: `rebase-legacy-reader`
   - **Expiration**: Set a bounded lifespan (e.g., 7 to 30 days).
   - **Resource owner**: Select the account or organization that owns the legacy repository.
4. **Repository access**:
   - Select **Only select repositories**.
   - Pick specifically the legacy repositories targeted for modernization in Rebase.
5. **Repository permissions**:
   - **Contents**: Select **Read-only**.
   - Leave all other permissions as **No access** (no Administration, Metadata, Issues, Workflows, or Pull Requests permissions are required).
6. **Organization Approval**:
   - If the repository resides in an organization requiring SAML/SSO or administrator token approval, ensure the organization administrators approve the token before using it.
7. **Copy Token**: The token string will start with `github_pat_`. Save it in a local password manager.

> [!IMPORTANT]
> Never grant **Write**, **Admin**, or **Workflow** permissions. Rebase only inspects and modernizes read-only snapshots and never pushes code directly to the source repository.

---

## 2. Security Guarantees and Architecture

Rebase enforces multiple concentric security controls to ensure PAT tokens remain ephemeral, isolated, and strictly bounded:

```
+---------------------------------------------------------------------------------------------------+
| Browser Frontend (CreateJob.tsx)                                                                  |
| - Token stored ONLY in component memory state (useState)                                          |
| - Masked input type="password" with toggle                                                        |
| - Never written to localStorage, sessionStorage, query params, or console logs                    |
+-------------------------------------------------+-------------------------------------------------+
                                                  | HTTPS Request Body (JSON)
                                                  v
+---------------------------------------------------------------------------------------------------+
| FastAPI Backend                                                                                   |
| - Token received in StackDetectionRequest or JobCreateRequest / JobIntakeRequest body             |
| - NEVER stored in PostgreSQL jobs table, stack_metadata, or audit_events                          |
| - Automated regex scrubbing in logging middleware (ghp_* and github_pat_* -> [REDACTED])          |
| - Target host validated: strictly restricted to github.com (non-GitHub hosts rejected)            |
+-------------------------------------------------+-------------------------------------------------+
                                                  | Ephemeral Git Credential Helper
                                                  v
+---------------------------------------------------------------------------------------------------+
| ControlledGitAdapter & Git Credential Helper                                                      |
| - Isolated OS temp directory with restrictive filesystem permissions                              |
| - In-memory Git config: -c credential.helper= -c credential.https://github.com.helper=!...       |
| - Helper Python script only answers if protocol=https and host=github.com                         |
| - Token NEVER passed as CLI argument (invisible to ps / Get-Process)                             |
| - Token secret file overwritten with zero bytes before unlinking and directory deletion           |
| - Subprocess safety: core.hooksPath=/dev/null, symlinks=false, redirects disabled                 |
+---------------------------------------------------------------------------------------------------+
```

---

## 3. Credential Lifecycle: Preview vs. Intake

Repository acquisition occurs in two distinct stages:

### Stage 1: Ephemeral Preview Detection (`POST /api/v1/jobs/detect-stack`)
1. User provides Repository URL and Revision in the Create Job wizard.
2. **Conditional Token Input**: For public repositories, the Access Token section is completely hidden. The section only appears when the user enables the **Private Repository** toggle or when ephemeral detection encounters a private repository authentication challenge (`401 / Authentication required`).
3. The frontend sends `access_token` in the request body to `/api/v1/jobs/detect-stack`.
3. `ControlledGitAdapter` creates an ephemeral credential helper and clones a shallow snapshot (`--depth 1`) into an OS temporary directory (`rebase_preview_*`).
4. `RepositoryInventoryScanner` scans manifests and DDL files, extracts language statistics, and builds the Three-Tier Architecture breakdown.
5. The exact commit hash is resolved (`git rev-parse HEAD`) and pinned as `resolved_commit`.
6. Ephemeral workspace and credential helper directories are purged immediately in a `finally` block.
7. Results are returned to the client. No permanent workspace or database row is created.

### Stage 2: Job Creation and Intake (`POST /api/v1/jobs` & `POST /api/v1/jobs/{job_id}/intake`)
1. When the user confirms the configuration, the job is created with status `CREATED`.
2. The user provides `git_token` (held in component memory).
3. The intake process initiates `ControlledGitAdapter.clone_repository()` to establish the permanent workspace in `repo_workspaces/job_{job_id}`.
4. **Pinned Commit Enforcement**: If `pinned_commit` was captured during preview, `ControlledGitAdapter` explicitly checks out that exact SHA. If the commit is missing or does not match, acquisition fails with status 404/409, preventing silent branch drift.
5. `AuditEvent` records `JOB_INTAKE_COMPLETED` with resolved commit and directory metadata, without token leakage.
6. The credential helper is wiped and removed immediately after acquisition.

---

## 4. Error Diagnostics and Troubleshooting

Rebase intercepts raw Git stderr and maps upstream GitHub responses to clear, actionable error envelopes:

| Upstream Cause | Sanitized Diagnostic Message | HTTP Status | Remediation |
| :--- | :--- | :--- | :--- |
| **Missing Token for Private Repo** | `Authentication required: Repository is private or inaccessible without a GitHub Personal Access Token (PAT).` | **401** | Enter a fine-grained PAT with Contents: Read-only access in the Private Repository section. |
| **Invalid or Expired Token** | `GitHub authentication failed: The provided Personal Access Token is invalid, expired, or revoked.` | **401** | Verify token expiration in GitHub and generate a replacement. |
| **SAML / SSO Enforcement** | `GitHub organization policy restriction: The Personal Access Token must be authorized for SAML/SSO by the repository owner organization.` | **403** | Authorize the PAT under organization SAML Single Sign-On. |
| **Repository Not Found or Access Denied** | `Repository not found or access denied: Verify repository URL and ensure the PAT has Contents (Read-only) permissions.` | **404** | Confirm repository name spelling and verify the PAT is granted access to this specific repository. |
| **API Rate Limit Exceeded** | `GitHub rate limit exceeded: Secondary or API rate limit reached. Please wait before retrying.` | **429** | Wait a few minutes before retrying or use an authenticated PAT for higher rate limits. |
| **Network Timeout** | `Network timeout while communicating with repository host.` | **504** | Check local internet connectivity or GitHub status. |

---

## 5. Local-Development Trust Boundary & Production Roadmap

### Residual Local Trust Boundary
- In local development, the backend executes under the local developer's user account.
- Any process running under the same OS user account with permissions to inspect the user's `Temp` directory or read memory could theoretically access temporary files during the clone execution window.
- The platform mitigates this by using restrictive permissions, random directory prefixes, and zero-byte file wiping immediately upon completion.

### Production Multi-Tenant Deployment Requirements
Before deploying Rebase to a shared multi-tenant production environment:
1. **Hardware Security Module / Secrets Manager**: Integrate with HashiCorp Vault, AWS Secrets Manager, or GCP Secret Manager to hold credentials in memory-encrypted envelopes.
2. **Short-Lived GitHub App Tokens**: Migrate from operator-supplied PATs to GitHub App Installations with transient installation access tokens (1 hour maximum lifespan).
3. **Egress Network Filtering**: Restrict outbound worker container connections strictly to approved GitHub IP address ranges and port 443.
4. **Sandbox Containers**: Execute Git clone operations inside isolated microVMs or gVisor sandbox containers with ephemeral RAM-backed filesystems.
