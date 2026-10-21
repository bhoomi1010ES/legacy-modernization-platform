# Phase 0 Architectural Flowcharts: Multi-Agent Legacy Code Modernization Platform

**Document:** `docs/phase-0/flowcharts.md`  
**Phase:** Phase 0 (Discovery, Architecture & Visual Specifications)  
**Date:** October 19, 2026  
**Status:** Completed  
**Author:** Principal Software Architect & Multi-Agent Systems Architect  

---

## Flowchart A: Phase 0 Implementation Workflow

```mermaid
flowchart TD
    A[1. Mandatory Initial Investigation] --> B[2. Initial Gap-Analysis Report]
    B --> C[3. Requirements Traceability Matrix & V1 Scope]
    C --> D[4. System Architecture & Component Mapping]
    D --> E[5. Domain Model & Job State Machine]
    E --> F[6. Security Threat Model & Gate Policies]
    F --> G[7. Versioned API & Agent Contracts]
    G --> H[8. TDD Minimal Backend Scaffolding]
    H --> I[9. Contract & Domain Policy Tests Pytest]
    I --> J[10. Frontend Alignment & Build Validation]
    J --> K[11. Architecture Sign-off & Completion Report]
```

---

## Flowchart B: Complete Platform Architecture

```mermaid
flowchart LR
    subgraph Client ["Client Tier"]
        UI[Browser UI React 19]
    end

    subgraph Gateway ["Control Gateway"]
        API[FastAPI Gateway /api/v1]
        AUTH[AuthN / AuthZ Service]
    end

    subgraph CoreServices ["Core Services"]
        JOB[Job Lifecycle Service]
        GATE[Gate Service G1-G4]
        ART[Artifact Service]
        AUDIT[Audit Service]
    end

    subgraph Supervisor ["Orchestration Tier"]
        SUP[LangGraph Supervisor]
        CP[(State Checkpoints)]
    end

    subgraph AgentTier ["Agent Reasoning Tier"]
        AG[Specialist Agents]
        GW[Model Gateway]
        TR[Tool Registry]
    end

    subgraph SandboxTier ["Execution Tier"]
        SB[Container Sandbox]
        VER[Verification Engine]
    end

    subgraph StorageTier ["Persistence Tier"]
        PG[(PostgreSQL 16)]
        S3[(S3 Object Store)]
        GIT[Git Repositories]
    end

    UI -->|HTTPS / Session Cookie| API
    API --> AUTH
    API --> JOB
    API --> GATE
    API --> ART
    API --> AUDIT

    JOB --> SUP
    SUP --> CP
    CP --> PG

    SUP --> AG
    AG --> GW
    AG --> TR
    TR --> SB
    SB --> VER
    SB --> GIT

    ART --> S3
    AUDIT --> PG
    JOB --> PG
```

---

## Flowchart C: Authentication & Session Lifecycle Flow

```mermaid
sequenceDiagram
    autonumber
    actor U as User (Browser)
    participant UI as Frontend App
    participant API as FastAPI /api/v1/auth
    participant DB as PostgreSQL User Store

    U->>UI: Enter email & password
    UI->>API: POST /auth/login {email, password}
    API->>DB: Query user by email
    DB-->>API: User record + password_hash (Argon2id)
    API->>API: Verify password hash
    
    alt Invalid Credentials
        API-->>UI: 401 Unauthorized ("Invalid email or password")
        UI-->>U: Display error message
    else Valid Credentials
        API->>DB: Create session record (session_id, user_id, expires_at)
        API-->>UI: 200 OK + Set-Cookie: session_id (HttpOnly, Secure, SameSite=Lax)
        UI->>API: GET /auth/me (Cookie automatically sent)
        API-->>UI: 200 OK {user_id, email, roles, permissions}
        UI-->>U: Render authenticated workspace
    end
```

---

## Flowchart D: Modernization Job Lifecycle

```mermaid
flowchart TD
    START([Job Submitted]) --> INTAKE[Intake: Clone Repo & Scan]
    INTAKE --> ANALYZE[Analyze: AST Parse & Map Dependencies]
    ANALYZE --> G1{Gate G1: Feasibility Approval}
    
    G1 -- Approved --> CHAR[Characterize: Capture Legacy Behavior]
    G1 -- Rejected --> RE_ANALYZE[Re-analyze or Cancel]
    
    CHAR --> G2{Gate G2: Freeze Test Suite}
    G2 -- Approved --> PLAN[Plan: Architecture Blueprint & Wave DAG]
    G2 -- Rejected --> CHAR
    
    PLAN --> G3{Gate G3: Plan & Architecture Approval}
    G3 -- Approved --> CONV[Convert: CodeWriter Sandbox Branches]
    G3 -- Rejected --> PLAN
    
    CONV --> VERIFY[Verify: Replay Frozen Tests]
    VERIFY -- Regression Loop <= 3 --> CONV
    VERIFY -- Verified --> INTEGRATE[Integrate: Merge & Draft PR]
    
    INTEGRATE --> G4{Gate G4: Final Delivery Approval}
    G4 -- Approved --> DONE([Job Completed: PR Ready for Merge])
    G4 -- Rejected --> CONV
```

---

## Flowchart E: Multi-Agent Collaboration Workflow

```mermaid
sequenceDiagram
    autonumber
    participant S as Supervisor
    participant A1 as Intake Agent
    participant A2 as Legacy Analyzer
    participant A3 as Characterizer
    participant A4 as CodeWriter
    participant A5 as Verifier
    participant ART as Artifact Store (S3)

    S->>A1: Task: Ingest repository
    A1->>ART: Store RepoInventory v1
    A1-->>S: Complete (RepoInventory v1 hash)

    S->>A2: Task: Map AST & capabilities
    A2->>ART: Store LegacyModel v2 & FeasibilityReport v1
    A2-->>S: Complete (G1 evidence ready)

    Note over S: [Human Approves Gate G1]

    S->>A3: Task: Capture tests
    A3->>ART: Store CharacterizationSuite v1
    A3-->>S: Complete (G2 suite hash frozen)

    Note over S: [Human Freezes G2 & Approves G3]

    S->>A4: Task: Convert Module 'Customer'
    A4->>ART: Store ModuleArtifact (branch: job/248/customer)
    A4-->>S: Complete (Module compiled)

    S->>A5: Task: Replay frozen suite against module
    A5->>ART: Store EquivalenceReport v2
    A5-->>S: Complete (98.6% Equivalence)
```

---

## Flowchart F: Inner Loop vs. Outer Loop Architecture

```mermaid
flowchart TB
    subgraph OuterLoop ["Outer Loop (Supervisor Control Plane)"]
        S_START[Stage Progression] --> CHECK_BUDGET{Budget Remaining?}
        CHECK_BUDGET -- No --> S_PAUSE[Pause Job & Alert Reviewer]
        CHECK_BUDGET -- Yes --> S_ASSIGN[Assign Task to Specialist Agent]
        S_ASSIGN --> INNER_EXEC[[Execute Inner Loop]]
        INNER_EXEC --> EVAL_RESULT{Evaluate Artifact Schema}
        EVAL_RESULT -- Valid Artifact --> S_CHECKPOINT[Persist Checkpoint to PostgreSQL]
        EVAL_RESULT -- Failure / Escalation --> S_ESCALATE[Escalate or Retry Stage]
        S_CHECKPOINT --> GATE_CHECK{Human Gate Required?}
        GATE_CHECK -- Yes --> S_HALT[Halt & Await Human Gate Decision]
        GATE_CHECK -- No --> S_START
    end

    subgraph InnerLoop ["Inner Loop (Specialist Agent Execution Plane)"]
        I_START[Receive Assignment] --> I_REASON[Reason & Formulate Action]
        I_REASON --> I_TOOL[Call Permitted Tool from Registry]
        I_TOOL --> I_SANDBOX[Execute Tool in Rootless Container]
        I_SANDBOX --> I_OBSERVE[Observe Sandbox Output / Compiler Output]
        I_OBSERVE --> I_TERM{Termination Condition?}
        I_TERM -- Continue --> I_REASON
        I_TERM -- Valid Output --> I_RETURN[Return Validated JSON Payload]
        I_TERM -- Exceeded Quota --> I_FAIL[Return Escalation / Quota Error]
    end

    INNER_EXEC -.-> I_START
    I_RETURN -.-> EVAL_RESULT
    I_FAIL -.-> S_ESCALATE
```

---

## Flowchart G: Human Approval Gate Workflow (G1–G4)

```mermaid
sequenceDiagram
    autonumber
    actor R as Human Reviewer
    participant UI as Browser UI
    participant G as Gate Service
    participant DB as PostgreSQL
    participant S as LangGraph Supervisor

    S->>G: Gate required (G1, G2, G3, or G4)
    G->>DB: Insert gate_decision row (status = PENDING)
    G-->>S: Workflow HALTED at checkpoint

    R->>UI: Navigate to /approvals
    UI->>G: GET /api/v1/gates/pending
    G-->>UI: Return pending gate + artifact hashes
    UI-->>R: Display evidence, capability gaps & risk analysis

    R->>UI: Select resolutions, write review rationale (min 10 chars), click Approve
    UI->>G: POST /api/v1/jobs/{id}/gates/{gate_id}/decisions {decision: "APPROVED", rationale: "..."}
    
    G->>G: Validate human session & REVIEWER role
    G->>G: Validate rationale length >= 10
    
    G->>DB: Update gate_decision (status = APPROVED, decided_at = NOW())
    G->>DB: Insert audit_event (GATE_APPROVED, actor = user_id)
    
    G-->>UI: 200 OK {decision_id, status: "APPROVED"}
    G->>S: Signal Gate APPROVED (Pass decision token)
    Note over S: Workflow RESUMES to next stage
```
