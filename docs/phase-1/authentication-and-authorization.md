# Authentication & Authorization Architecture
## Phase 1 Identity, Session Lifecycle and Access Control

**Document:** `docs/phase-1/authentication-and-authorization.md`  
**Phase:** Phase 1 (Security & Identity Implementation)  
**Date:** October 19, 2026  
**Status:** Completed & Verified  

---

## 1. Authentication Strategy & Session Lifecycle

The platform enforces **server-validated, stateful sessions** using HttpOnly cookies to protect single-page application browser users against token exfiltration (XSS) and cross-site request forgery (CSRF).

```mermaid
sequenceDiagram
    autonumber
    actor User as Browser / User
    participant API as FastAPI Gateway
    participant Auth as AuthService
    participant DB as PostgreSQL (users, sessions, audit)

    User->>API: POST /api/v1/auth/login {email, password}
    API->>Auth: authenticate_user(email, password, ip, user_agent)
    Auth->>Auth: Check brute-force rate limit (<= 5 attempts / 15 min)
    Auth->>DB: Query User by email
    Auth->>Auth: Verify password against bcrypt hash (rounds=12)
    alt Invalid Credentials or Non-Existent User
        Auth->>DB: Record LOGIN_FAILED audit event
        Auth-->>API: 401 Unauthorized ("Invalid email or password.")
        API-->>User: Generic Error Envelope
    else Valid Credentials
        Auth->>DB: Invalidate previous active sessions (Session Rotation)
        Auth->>Auth: Generate 256-bit secure session token
        Auth->>Auth: Calculate SHA-256 token_hash
        Auth->>DB: Insert UserSession (token, expiry = now + 24h)
        Auth->>DB: Record LOGIN_SUCCESS audit event
        Auth-->>API: (User, session_token, permissions)
        API-->>User: 200 OK + Set-Cookie (rebase_session_id; HttpOnly; SameSite=Lax; Path=/)
    end

    Note over User,DB: Subsequent Authenticated Requests
    User->>API: GET /api/v1/auth/me (Cookie: rebase_session_id)
    API->>Auth: get_user_from_session(token)
    Auth->>DB: Query UserSession where is_revoked = false
    Auth->>Auth: Verify absolute timeout (< 24h) & idle timeout (< 4h)
    Auth->>DB: Update last_activity_at = now()
    Auth-->>API: User safe profile (no secrets or hashes)
    API-->>User: 200 OK {user_id, email, full_name, role, permissions}

    Note over User,DB: Session Invalidation
    User->>API: POST /api/v1/auth/logout
    API->>Auth: logout(token)
    Auth->>DB: Update is_revoked = true, Record LOGOUT audit event
    API-->>User: 200 OK + Clear Cookie
```

### Security Invariants
1. **Unpredictable Token Entropy:** Tokens are generated via `secrets.token_urlsafe(32)` providing 256 bits of cryptographic entropy.
2. **Server-Side Session Record:** Stored in `user_sessions` with SHA-256 token hash, client IP address, user agent, expiration, and revocation status.
3. **Session Rotation:** On successful login, all prior active sessions for that user are marked `is_revoked = true` to prevent session fixation.
4. **Dual Expiry Windows:**
   - **Idle Timeout:** 4 hours of inactivity triggers automatic invalidation.
   - **Absolute Lifetime:** 24 hours ceiling.
5. **Brute-Force Rate Limiting:** Maximum 5 failed attempts per IP/email pair in a 15-minute sliding window before triggering temporary lockout.
6. **Information Disclosure Prevention:** Generic `"Invalid email or password."` messages prevent username enumeration attacks.

---

## 2. Resource-Level Authorization & Tenancy Isolation

Global roles alone do not grant access to operational data. The platform implements **Job-Scoped Multi-Tenancy** enforced by `require_job_access`:

```mermaid
graph TD
    REQ[HTTP Request to /jobs/{job_id}/*] --> AUTH[Extract & Validate Session]
    AUTH -- No Session / Expired --> E401[401 Unauthorized]
    AUTH -- Valid Session --> ROLE_CHK{Global SUPER_ADMIN?}
    ROLE_CHK -- Yes --> ALLOW[Grant Access]
    ROLE_CHK -- No --> DB_MEM{Query JobMembership for User + Job}
    DB_MEM -- No Record Found --> E404[404 Not Found (IDOR Mask)]
    DB_MEM -- Member Found --> PERM_CHK{Role Grants Required Permission?}
    PERM_CHK -- Yes --> ALLOW
    PERM_CHK -- No --> E403[403 Forbidden]
```

### IDOR Defense Policy
When an unauthorized user attempts to query a job ID, artifact ID, or audit trail they do not belong to:
- The API returns **`404 Not Found`** instead of `403 Forbidden`.
- This ensures an attacker cannot probe sequential or guessed UUIDs to discover whether sensitive corporate jobs exist.

### Role Capability Matrix

| Permission | SUPER_ADMIN | ADMIN | REVIEWER | DEVELOPER | VIEWER |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `job:create` | Yes | Yes | No | No | No |
| `job:read` | Yes | Yes | Yes | Yes | Yes |
| `job:pause_resume` | Yes | Yes | Yes | No | No |
| `job:cancel` | Yes | Yes | No | No | No |
| `gate:approve_g1..g4` | Yes | Yes | Yes | No | No |
| `artifact:read` | Yes | Yes | Yes | Yes | Yes |
| `artifact:download` | Yes | Yes | Yes | Yes | No |
| `audit:read` | Yes | Yes | Yes | Yes | No |
| `user:manage` | Yes | No | No | No | No |
