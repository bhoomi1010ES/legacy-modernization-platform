# Spendwise Legacy Runtime

This directory provides the sandboxed runtime adapter for Spendwise modernization behavioral characterization (Phase 5 Gate G2).

## Components

- `adapter.py`: Standalone adapter conforming to the strict Phase 5 stdin/stdout JSON protocol.
  - Receives `{"scenario": str, "inputs": dict}` on standard input.
  - Emits `{"output": dict, "side_effects": dict}` on standard output.
- `Dockerfile`: Minimal alpine-based container running strictly under rootless user `65534:65534` (nobody/nogroup) with `--read-only`, `--network=none`, and `--cap-drop=ALL`.

## Local Build

```bash
docker build -t spendwise-legacy-runtime:v1 tools/legacy_runtimes/spendwise/
```

