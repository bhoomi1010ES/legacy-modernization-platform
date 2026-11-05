# Operational Runbook: Secret & Credential Key Rotation

> **Audience:** Security Engineers, SRE, Platform Administrators  
> **Classification:** Production Operational Runbook (Phase 8)  
> **Last Verified:** 2026-11-05  

---

## 1. Scope & Objective

This runbook defines the procedures for rotating all credentials, API tokens, cryptographic secrets, and passwords used by the platform with zero downtime and zero data corruption:
1. **OpenAI API Key (`OPENAI_API_KEY`)**
2. **Platform Session Encryption Secret (`SECRET_KEY`)**
3. **GitHub Personal Access Token (`PHASE7_GITHUB_TOKEN`)**
4. **PostgreSQL Database Password (`DATABASE_URL`)**

---

## 2. Key Rotation Schedule & Triggers

| Credential | Standard Rotation Frequency | Emergency Trigger |
|---|---|---|
| `OPENAI_API_KEY` | Every 90 days | Token leakage, rate limit compromise, provider alert |
| `SECRET_KEY` | Every 180 days | Compromise of session cookies, security audit finding |
| `PHASE7_GITHUB_TOKEN` | Every 60 days | Developer offboarding, fine-grained PAT expiration |
| PostgreSQL Password | Every 90 days | SRE team changes, unauthorized DB connection logs |

---

## 3. Step-by-Step Rotation Procedures

### SOP-KR-01: OpenAI API Key Rotation

1. **Generate New Key:**
   - Log in to OpenAI Organization Console -> API Keys -> Create new secret key (`rebase-prod-2026-q4`).
   - Copy key value: `sk-proj-...`
2. **Validate New Key Standalone:**
   ```bash
   curl https://api.openai.com/v1/models \
     -H "Authorization: Bearer sk-proj-<NEW_KEY>"
   ```
3. **Update Environment Configuration:**
   - In deployment secrets manager or `.env`:
     ```ini
     OPENAI_API_KEY=sk-proj-<NEW_KEY>
     ```
4. **Reload Service (Zero-Downtime Rolling Restart):**
   - Perform rolling restart of backend API workers:
     ```bash
     systemctl reload rebase-backend.service
     ```
5. **Verify Live Conversion Worker:**
   - Check `model_gateway` health endpoint or run a lightweight test prompt.
6. **Revoke Old Key:**
   - Return to OpenAI Console and delete the deprecated key after confirming zero failed API calls.

---

### SOP-KR-02: Platform Session Secret Key Rotation (`SECRET_KEY`)

The `SECRET_KEY` is used for signing secure HttpOnly session cookies. Rotating this key invalidates active user sessions, requiring re-login.

1. **Generate Cryptographically Secure 64-Byte Key:**
   ```powershell
   $bytes = New-Object byte[] 48
   [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
   [Convert]::ToBase64String($bytes)
   ```
2. **Schedule Maintenance Window:**
   - Notify users 24 hours in advance that active browser sessions will be refreshed.
3. **Update Configuration:**
   ```ini
   SECRET_KEY=<NEW_GENERATED_BASE64_STRING>
   ```
4. **Restart API Service:**
   ```bash
   systemctl restart rebase-backend.service
   ```
5. **Verify Session Enforcement:**
   - Test that old session cookies receive HTTP 401 Unauthorized.
   - Verify that logging in via `/api/v1/auth/login` sets a valid cookie and `/api/v1/auth/me` returns HTTP 200.

---

### SOP-KR-03: GitHub Fine-Grained PAT Rotation

1. **Generate GitHub PAT:**
   - Repository Settings -> Developer Settings -> Fine-Grained Personal Access Tokens.
   - Grant repository read/write access restricted strictly to target delivery repositories.
2. **Update Environment:**
   ```ini
   PHASE7_GITHUB_TOKEN=github_pat_<NEW_TOKEN>
   ```
3. **Verify Git Authentication:**
   ```python
   # Verify PAT in isolated subprocess
   from app.core.git import ControlledGitAdapter
   adapter = ControlledGitAdapter()
   # verify clone / push without token exposure
   ```
4. **Revoke Old PAT:**
   - Delete old token from GitHub Developer Settings.

---

### SOP-KR-04: PostgreSQL Database Password Rotation

1. **Create Alternate User / Update Password in PostgreSQL:**
   ```sql
   ALTER USER postgres WITH PASSWORD '<NEW_STRONG_PASSWORD>';
   ```
2. **Update Application Connection String:**
   ```ini
   DATABASE_URL=postgresql+asyncpg://postgres:<NEW_STRONG_PASSWORD>@127.0.0.1:5432/rebase
   ```
3. **Restart Backend Connection Pool:**
   ```bash
   systemctl restart rebase-backend.service
   ```
4. **Verify Health:**
   - Query `/api/v1/health` and verify DB connectivity returns `status: "healthy"`.

