# Go/Fiber characterization adapter review — 2026-11-02

## Status

**Blocked from controller approval.** The image builds from the pinned job source, but its required Trivy scan found critical/high vulnerabilities. The image and adapter were not added to the controller allowlist, and no customer application code was executed in it.

## Candidate binding

- Job: `f7755169-0ecd-49ed-b1ca-80bab89e9711` (`Nextjs Golang Crud App Modernization`)
- Source commit: `b6c4d278589e9e467c64ef9c5f3b8b50726f4726`
- Snapshot SHA-256 (tracked source excluding the documented executable): `4bb71c4b6c342f095442e2df6365ee06d2cffa0e276e255b09da71a8ec8004bd`
- Excluded tracked executable: `bin/main`, 21,908,567 bytes, SHA-256 `d1c3f09dbea404abcfab0066ba0bb4128c4d28a44ebf13ee82ade075abe55a91`
- Exclusion reason: the pinned image compiles the app from the bound Go source; forwarding the stale prebuilt binary exceeded the controller's request limit. The exclusion is bound into the Phase 5 candidate hash and persisted execution provenance.
- Go builder base: `golang:1.24.13-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac`
- Runtime base: `ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852`
- Built local image candidate: `sha256:841bd47fdeb78a682d4429ca6d9faad8355d733555ed996fa708cfc24836e2ce`
- Adapter SHA-256: `53c5fb19cb23dfc559aa96b294daab737b856a1002717e696229f6cec27b01dc`
- Image config declares UID/GID `65534:65534`; actual sandbox configuration was not observed because controller launch was blocked by the vulnerability scan.

## Security review

Trivy `0.76.1` scanned the local image using the database updated `2026-11-02T07:17:05Z`. Full output is in `W09_GO_FIBER_IMAGE_SCAN_20261102.json`.

- Critical: 3
- High: 37
- Medium: 55
- Low: 9
- Unknown: 2

Critical Go module findings include Fiber `v2.52.9` (`CVE-2025-66630`, fixed in `2.52.11`) and pgx `v5.5.2` (`CVE-2026-33815`, `CVE-2026-33816`, fixed in `5.9.0`). The independent controller's policy rejects images with high/critical findings. No waiver was fabricated and the existing allowlist was left unchanged.

## Adapter scope

The reviewed adapter starts the actual compiled Fiber application against a fresh PostgreSQL 16 database in the sandbox scratch filesystem and captures HTTP responses plus database state for the existing frozen module fixtures:

- `bootstrap`: Swagger route response and created tables.
- `database`: migrated `users` schema and rows.
- `middleware`: unauthenticated API response and before/after database rows.
- `repository`: user creation, login, authenticated listing, and resulting database rows.
- `images`: remains unobserved; no image behavior is declared by the application routes.
- `frontend`: remains unobserved until a pinned browser/DOM runtime and controlled Next.js dependency build are approved. Static file checks are not used as behavioral evidence.

Phase 5 already repeats an available observation in a second independent container and compares normalized output and side effects. The adapter returns explicit `UNOBSERVED` reasons for image/frontend scenarios; the API preserves adapter stderr as the row limitation. Neither the backend replay nor any of the six frozen scenarios ran because the candidate image failed scan review.

## UI and local regression evidence

The G2 matrix now displays each unavailable case's concrete `limitation` (falling back to sanitized stderr, then an explicit unknown reason). The exact 8 MiB failure from the prior run therefore appears on its row rather than being hidden behind a generic mode label.

- Frontend characterization test: **9 passed**.
- Frontend TypeScript/Vite production build: **passed** (Vite reports its existing >500 kB chunk advisory).
- Snapshot exclusion safety tests: **3 passed**.
- Phase 5 sandbox evidence and adapter-reason tests: **2 passed**.

## Required next action

Remediate the source dependency findings (including Fiber and pgx) in a separately reviewed source revision, then refresh the characterization candidate binding and obtain any required G2 approval. Rebuild and rescan the image before requesting controller approval. Provision and approve a pinned browser/DOM image to make the frontend row executable. Until then these six rows must not be represented as passing behavior-equivalence evidence.
