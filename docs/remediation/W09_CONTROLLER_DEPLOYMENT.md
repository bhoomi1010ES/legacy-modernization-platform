# W09 controller deployment — current state

Current acceptance status: **W09 IN PROGRESS**. See the [current W09 status report](../audits/W09_STATUS_20261102.md). The earlier long-form blocker matrix is retained as historical inspection evidence; its deployment statements are superseded by that report.

## Installed and verified in Ubuntu WSL

- Rootless Docker 29.9.2, using `runc` (gVisor is not selected).
- Separate `rebase-sandbox-controller.service`, bound to WSL loopback on port 8093, with a durable SQLite queue and worker lease recovery.
- Private controller configuration at `~/.config/rebase/sandbox-controller.json` with mode `0600`; control-plane database, OpenAI and cloud credentials are not passed to the worker/container.
- Reviewed images are allowlisted by immutable digest. Actual runtime preflight and per-container configuration are checked.
- Trivy 0.76.1 and vulnerability DB are installed; the pinned image scan ran and passed with no blocking findings.
- `/dev/sdf` is configured for block I/O enforcement at 10 MiB/s read and write. Container and kernel `io.max` evidence was collected.
- Controller systemd unit sets `LimitNOFILE=4096`. WSL API and Vite proxy both route correctly to the WSL PostgreSQL-backed API.

The rootless controller and API currently authenticate to each other. Direct controller health reports a live worker and both approved images. API `/api/v1/health` returns HTTP 200 with PostgreSQL connected. API `/api/v1/readiness` returns HTTP 503 because the configured target verification profile is incomplete; this is expected fail-closed behavior.

## Current sandbox evidence

- [Controller deployment](../audits/W09_CONTROLLER_DEPLOYMENT_20261102.json)
- [I/O limits](../audits/W09_IO_LIMITS_20261102.json)
- [Trivy installation](../audits/W09_TRIVY_INSTALL_20261102.json)
- [Hostile code probes](../audits/W09_CONTAINMENT_20261102_R3.json): 15 PASS, 0 FAIL
- [Worker crash recovery](../audits/W09_WORKER_CRASH_20261102_R4.json): task blocked, orphan cleaned, replacement worker ready
- [Live migration preservation](../audits/W09_LIVE_MIGRATIONS_20261102.json)

Diagnostic probes are not delivery verification evidence. A diagnostic run cannot authorize a module, integration, human gate, or ZIP.

## Remaining infrastructure action

The current reviewed image only supports the calculator fixture. `PHASE6_TARGET_PROFILES_JSON` is currently empty, so no job target can select a profile. Legacy global Phase 6/7 command settings are not accepted as substitutes. W09 requires approved target-stack profiles for the actual PHP/Node project, including unit/integration, static and security checks, dependency vulnerability and license policy scans, database migration compatibility, API compatibility, and browser/DOM behavior. The old Phase 7 settings use compile-only commands under several labels and are correctly rejected by the profile validator.

Each registry entry is keyed by the exact normalized `Job.target_stack` and has these required fields: `version`, `image` (immutable digest), `runtime`, `timeout`, `adapter`, `checks`, and `system_checks`. Both check arrays are validated before candidate execution. The frozen profile and digest are stored in `VerificationRun`; changing the profile requires a new independent run.

Before installing additional execution tools or rebuilding reviewed images, obtain human approval for a pinned PHP/Composer/Node/browser toolchain and its advisory/license data provisioning. Keep network disabled during code execution; any vulnerability/advisory database refresh belongs to trusted provisioning. After that action, rebuild and pin images, run Trivy, configure stack-specific command profiles, and rerun independent verification against the exact candidate and frozen suite.

Do not reuse the calculator adapter for PHP/Node/customer scenarios. Missing profiles or executables remain `NOT_RUN`/`BLOCKED`; static file presence does not establish runtime or behavioral parity.
