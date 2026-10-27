# Phase 6 local acceptance evidence

The non-secret configuration template is `acceptance.env.example`. Copy it to local `acceptance.env` only when reproducing this fixture. The pinned local image must exist first; missing images are never pulled automatically. Do not run the model/gate drivers for a different job or without current human authorization.

These are one-off acceptance drivers, not a second platform workflow. They call the existing APIs, Supervisor and sandbox. The recorded G1/G2/G3 approvals apply only to the exact job/gate IDs the user reviewed in this session. Do not reuse them as approval for another job or changed evidence.

The pinned image was built offline from an already-local CPython runtime and locally installed pure-Python pytest/mypy/Bandit dependencies. The final scratch image excludes the donor application's code, environment and dependencies. No image was pulled and no registry/package installation occurred. Copied third-party tooling is ignored by Git.

`run.ps1` loads process-local settings from `acceptance.env` and restores the caller's environment. It does not modify the shared backend `.env` or expose credentials. The local settings bind the exact image and approved Qwen model. Provider credentials still come from the existing backend configuration. Never commit session cookies or credentials.

Run an individual non-model probe from the workspace root:

```powershell
powershell -ExecutionPolicy Bypass -File tools/phase6_acceptance/run.ps1
```

This invokes `run_sandbox.py`; its output explicitly labels trusted probe code as **not** model-generated output. `negative_sandbox.py` checks real Docker failures. `inspect_environment.py` observes Docker's actual container settings and cleanup. `collect_evidence.py` is read-only. The API checks authenticate normally and reject cross-job access/caller controls.

The fixture job is paused after a real OpenRouter HTTP 402. The user instructed us to leave model acceptance pending. Do not run a conversion/repair driver or change providers without renewed user direction. There is no successful model ChangeSet, model-backed repair or integration/G4 acceptance. Local `artifacts/phase6-real-acceptance/private-session.json` is sensitive; never share it with the report.

Build inputs were formatted after the tested image was built. Use the **image-internal SHA-256 values** in `environment.json` as evidence of what actually ran. A rebuild has a new immutable identity and must be revalidated; do not substitute the mutable tag for the report's pin.

See [the acceptance report](../../docs/phase6/PHASE6_REAL_ENVIRONMENT_ACCEPTANCE.md) for the actual scope, results and remaining blockers.
