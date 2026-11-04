# W01 — Authorization and RBAC Remediation Report

> **Document Type:** Workstream Authorization Architecture Report  
> **Workstream:** W01 (Authentication, Authorization & Gate Integrity)  
> **Environment:** `ENV-LOCAL-DEV-POSTGRES18` / Isolated Database `rebase_test_w01`  
> **Date:** 2026-10-30  
> **Status:** REMEDIATED & ENFORCED

---

## 1. Authorization Architecture Overview

The Legacy Modernization Platform implements a dual-layer Role-Based Access Control (RBAC) model:

1. **Global User Role (`User.role`):** Defines global administrative boundaries across the workspace (`SUPER_ADMIN`, `ADMIN`, `PROJECT_MANAGER`, `REVIEWER`, `DEVELOPER`, `VIEWER`).
2. **Contextual Job Membership (`JobMembership.role_id`):** Enforces scoped, job-specific capabilities on each modernized repository.

Prior to W01, this architecture suffered from two critical privilege escalation vectors:
- **`SEC-02`:** Public registration allowed self-selection of the `REVIEWER` role, granting immediate human gate review and approval powers to arbitrary accounts.
- **`SEC-03`:** Job creation automatically granted `JobMembership.role_id = "ADMIN"` to whoever created the job, elevating unprivileged developers and viewers into administrators capable of self-approving gates.

---

## 2. Implemented Authorization Safeguards

### 2.1 Least-Privilege Creator Role Assignment

In `backend/app/services/job_service.py:116–122`, the automatic `ADMIN` membership grant was eliminated:

```python
# SEC-03: Creators receive their role if administrative, or least-privilege DEVELOPER.
# Non-admin creators never get automatically elevated to ADMIN.
creator_job_role = user.role if user.role in ("ADMIN", "SUPER_ADMIN") else "DEVELOPER"
membership = JobMembership(
    job_id=job_id,
    user_id=user.user_id,
    role_id=creator_job_role,
)
db.add(membership)
```

- When a `DEVELOPER` creates a job, their job-level role is `DEVELOPER`.
- When a `VIEWER` creates a job, their job-level role is `DEVELOPER` (or they are blocked if lacking `job:create`).
- Job ownership is tracked strictly via `job.owner_user_id` without conflating ownership with platform administrative status.

### 2.2 Permissions Matrix by Role

The authoritative permissions matrix defined in `backend/app/domain/state_machine.py:106–138` (`RBACPolicy`):

| Permission Capability | SUPER_ADMIN | ADMIN | REVIEWER | DEVELOPER | VIEWER |
|---|:---:|:---:|:---:|:---:|:---:|
| `job:create` | Yes | Yes | No | No | No |
| `job:read` | Yes | Yes | Yes | Yes | Yes |
| `job:intake` | Yes | Yes | No | No | No |
| `job:pause_resume` | Yes | Yes | Yes | No | No |
| `job:cancel` | Yes | Yes | No | No | No |
| `gate:review` | Yes | Yes | Yes | Yes | Yes |
| `gate:approve_g1` | Yes | Yes | Yes | **No** | **No** |
| `gate:approve_g2` | Yes | Yes | Yes | **No** | **No** |
| `gate:approve_g3` | Yes | Yes | Yes | **No** | **No** |
| `gate:approve_g4` | Yes | Yes | Yes | **No** | **No** |
| `module:convert` | Yes | Yes | No | Yes | No |
| `module:repair` | Yes | Yes | No | Yes | No |
| `module:waive` | Yes | Yes | Yes | No | No |
| `artifact:read` | Yes | Yes | Yes | Yes | Yes |
| `artifact:download` | Yes | Yes | Yes | Yes | No |
| `artifact:publish_diagnostic` | Yes | Yes | No | Yes | No |
| `delivery:publish` | Yes | Yes | No | No | No |
| `audit:read` | Yes | Yes | Yes | Yes | No |
| `settings:update` | Yes | Yes | No | No | No |
| `user:manage` | Yes | No | No | No | No |

Notice that `DEVELOPER` role possesses **zero gate approval permissions** (`gate:approve_g*`). Consequently, a creator with `DEVELOPER` membership cannot approve any G1–G4 gate.

### 2.3 Administrative Role Assignment Workflow

To prevent self-escalation while providing a legitimate administrative path:
- A new endpoint `POST /api/v1/auth/users/{user_id}/role` was deployed in `backend/app/api/v1/auth.py:179–210`.
- Requires an active authenticated session belonging to `SUPER_ADMIN` or `ADMIN`.
- Validates that the requested target role is one of `{"SUPER_ADMIN", "ADMIN", "PROJECT_MANAGER", "REVIEWER", "DEVELOPER", "VIEWER"}`.
- Rejects requests from non-administrators with HTTP 403 `ForbiddenException`.
- Emits a transactional audit event `USER_ROLE_ASSIGNED` recording `actor_id`, `target_user_id`, and `new_role`.

---

## 3. Regression Verification

Verified by automated tests:
1. `test_w01_3_non_admin_creator_receives_developer_membership`: Verified database record has `role_id="DEVELOPER"`.
2. `test_job_membership_role_restrictions`: Proved `VIEWER` member cannot mutate job states (HTTP 403).
3. `test_job_isolation_non_member_access_denied`: Proved non-members are masked with HTTP 404 (anti-IDOR defense).
4. `test_w01_2_admin_role_assignment_flow`: Proved self-elevation is blocked and administrative elevation succeeds.

