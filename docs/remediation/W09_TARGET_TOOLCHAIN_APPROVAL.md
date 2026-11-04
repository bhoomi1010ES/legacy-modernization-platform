# W09 target-stack toolchain provisioning request

The independently leased WSL controller and pinned sandbox images are healthy, but the target-profile registry is intentionally empty. The current reviewed calculator image cannot truthfully verify the project's PHP/Node behavior, database migration compatibility, or browser interactions. Until complete target profiles exist, API readiness reports `sandboxes=profile_missing`, and production verification stays BLOCKED.

## Proposed bounded work

Build immutable, digest-pinned verification images inside Ubuntu WSL, using the versions and lockfiles declared by the project. Keep package installation in image-build time; keep generated customer code execution network-disabled. Scan each resulting image with the already approved Trivy installation and record the image digest and scan evidence.

The proposed profiles cover:

- PHP target: the project-declared PHP and Composer versions; project unit/integration test runner; PHP type/static and style checks; Composer advisory and license policy checks; target-database migration compatibility.
- Node target: the lockfile-selected Node/package-manager version; declared unit/integration tests; type/lint checks; package advisory and license policy checks.
- Browser behavior: pinned headless Chromium/Playwright checks against the served application for routes, links, forms, and observable DOM/state behavior.
- Full-system profile: distinct build, unit, integration, static, SAST, dependency, license, API/runtime, schema/migration and browser checks, with tool/version and command-profile evidence frozen per target profile.

Do not add a profile until its image is immutable, its actual commands are executable and distinct, tool versions are recorded, and expected test cases/assertions are defined. An unavailable target database flavor or browser check remains `NOT_RUN`/`BLOCKED`; it is not replaced with another database or a static HTML check.

## Human action needed

Approve provisioning these PHP, Node, and browser/DOM verification toolchains in the WSL image-build environment, including downloading the declared package-manager/browser artifacts and required vulnerability/advisory data. No provider request, customer-code network access, or human gate decision is part of this infrastructure change.
