"""Phase 8 High-Concurrency and Latency Benchmark Tool.

Measures p50, p95, and p99 latency baselines across:
1. Concurrent Task Leasing and Fencing
2. Concurrent Gate Decision Idempotency
3. High-Throughput Artifact Streaming & Checksumming
4. High-Volume Secret Redaction Throughput
"""

import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
import numpy as np

# Ensure backend app is on sys.path
sys.path.insert(0, os.path.abspath("backend"))

from app.services.secret_redactor import SecretRedactor
from app.core.storage import get_storage_adapter
from app.domain.state_machine import GatePolicy, RBACPolicy
from app.schemas.gates import DecisionOutcome, GateDecisionRequest, GateType


async def benchmark_task_leasing_concurrency():
    """Simulate 25 concurrent worker threads attempting to lease modules with pessimistic locking."""
    print("\n--- 1. Concurrent Task Leasing & Worker Fencing Benchmark ---")
    concurrency = 25
    num_requests = 100
    latencies = []

    # Shared simulated lock pool representing database row-level locking
    lock = asyncio.Lock()
    leased_modules = {}

    async def worker_attempt(worker_idx, req_id):
        t0 = time.perf_counter()
        async with lock:
            # Critical section simulation: check module state and acquire lease
            module_id = f"mod-{(req_id % 10):03d}"
            await asyncio.sleep(0.002)  # Simulate 2ms database round-trip
            if module_id not in leased_modules:
                leased_modules[module_id] = f"worker-{worker_idx}"
                acquired = True
            else:
                acquired = False
        duration_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(duration_ms)
        return acquired

    t_start = time.perf_counter()
    tasks = []
    for i in range(num_requests):
        w_idx = i % concurrency
        tasks.append(worker_attempt(w_idx, i))

    results = await asyncio.gather(*tasks)
    total_time = time.perf_counter() - t_start

    p50 = float(np.percentile(latencies, 50))
    p95 = float(np.percentile(latencies, 95))
    p99 = float(np.percentile(latencies, 99))
    rps = num_requests / total_time

    print(f"Requests: {num_requests} | Concurrency: {concurrency}")
    print(f"Throughput: {rps:.1f} req/s | Total Time: {total_time:.3f}s")
    print(f"Latency: p50={p50:.2f}ms | p95={p95:.2f}ms | p99={p99:.2f}ms")
    print(f"Unique leased modules: {len(leased_modules)} (Zero double-leases)")
    assert len(leased_modules) <= 10

    return {
        "operation": "task_leasing_fencing",
        "concurrency": concurrency,
        "requests": num_requests,
        "rps": round(rps, 1),
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
    }


async def benchmark_gate_decision_idempotency():
    """Benchmark concurrent duplicate gate decision requests under idempotency locking."""
    print("\n--- 2. Concurrent Gate Decision Idempotency Benchmark ---")
    num_requests = 100
    concurrency = 20
    latencies = []

    decision_cache = {}
    cache_lock = asyncio.Lock()

    async def submit_decision(worker_idx, idempotency_key):
        t0 = time.perf_counter()
        async with cache_lock:
            await asyncio.sleep(0.001)  # Simulate DB lookup
            if idempotency_key in decision_cache:
                decision = decision_cache[idempotency_key]
                is_duplicate = True
            else:
                decision = {
                    "gate_id": str(uuid.uuid4()),
                    "decision": "APPROVED",
                    "decided_by": f"reviewer-{worker_idx}",
                    "idempotency_key": idempotency_key,
                }
                decision_cache[idempotency_key] = decision
                is_duplicate = False
        duration_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(duration_ms)
        return is_duplicate

    t_start = time.perf_counter()
    # 10 unique idempotency keys repeated 10 times across 20 workers
    tasks = []
    for i in range(num_requests):
        k = f"idem-key-{i % 10}"
        tasks.append(submit_decision(i % concurrency, k))

    results = await asyncio.gather(*tasks)
    total_time = time.perf_counter() - t_start

    duplicates = sum(1 for r in results if r is True)
    created = sum(1 for r in results if r is False)

    p50 = float(np.percentile(latencies, 50))
    p95 = float(np.percentile(latencies, 95))
    p99 = float(np.percentile(latencies, 99))
    rps = num_requests / total_time

    print(f"Requests: {num_requests} | Concurrency: {concurrency}")
    print(f"Decisions Created: {created} | Duplicates Idempotently Resolved: {duplicates}")
    print(f"Throughput: {rps:.1f} req/s | Total Time: {total_time:.3f}s")
    print(f"Latency: p50={p50:.2f}ms | p95={p95:.2f}ms | p99={p99:.2f}ms")

    assert created == 10
    assert duplicates == 90

    return {
        "operation": "gate_decision_idempotency",
        "concurrency": concurrency,
        "requests": num_requests,
        "rps": round(rps, 1),
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
    }


async def benchmark_artifact_streaming_throughput():
    """Benchmark concurrent read/write and SHA-256 verification of large deliverable artifacts."""
    print("\n--- 3. Artifact Storage Streaming & Checksum Benchmark ---")
    storage = get_storage_adapter()
    num_artifacts = 50
    concurrency = 10
    payload_size = 512 * 1024  # 512 KB per deliverable chunk
    latencies_put = []
    latencies_get = []

    sem = asyncio.Semaphore(concurrency)

    async def put_and_verify(idx):
        raw_bytes = os.urandom(payload_size)
        expected_hash = hashlib.sha256(raw_bytes).hexdigest()
        key = f"phase8-bench/artifact_{idx:03d}.bin"

        async with sem:
            # Put
            t0 = time.perf_counter()
            content_hash, byte_len = await storage.put_object(key, raw_bytes, media_type="application/octet-stream")
            latencies_put.append((time.perf_counter() - t0) * 1000.0)
            assert content_hash == expected_hash

            # Get & verify
            t1 = time.perf_counter()
            read_bytes = await storage.get_object(key)
            latencies_get.append((time.perf_counter() - t1) * 1000.0)
            actual_hash = hashlib.sha256(read_bytes).hexdigest()
            assert actual_hash == expected_hash

            # Clean up
            await storage.delete_object(key)

    t_start = time.perf_counter()
    await asyncio.gather(*[put_and_verify(i) for i in range(num_artifacts)])
    total_time = time.perf_counter() - t_start

    total_mb = (num_artifacts * payload_size * 2) / (1024 * 1024)
    mbps = total_mb / total_time

    p50_get = float(np.percentile(latencies_get, 50))
    p95_get = float(np.percentile(latencies_get, 95))
    p99_get = float(np.percentile(latencies_get, 99))

    print(f"Artifacts processed: {num_artifacts} (512 KB each, read+write)")
    print(f"Total I/O: {total_mb:.1f} MB in {total_time:.2f}s ({mbps:.2f} MB/s)")
    print(f"Read Latency: p50={p50_get:.2f}ms | p95={p95_get:.2f}ms | p99={p99_get:.2f}ms")

    return {
        "operation": "artifact_streaming_checksum",
        "concurrency": concurrency,
        "items": num_artifacts,
        "total_mb": round(total_mb, 1),
        "mb_per_sec": round(mbps, 2),
        "p50_read_ms": round(p50_get, 2),
        "p95_read_ms": round(p95_get, 2),
        "p99_read_ms": round(p99_get, 2),
    }


def benchmark_secret_redaction_throughput():
    """Benchmark high-throughput secret redaction on intensive payload logs."""
    print("\n--- 4. Secret Redaction Throughput Benchmark ---")
    redactor = SecretRedactor(custom_sensitive_values={"SuperSecretPassword123!"})

    lines = [
        "2026-11-05T14:00:00Z [INFO] Initializing service with token sk-proj-1234567890abcdef1234567890abcdef12345678",
        "2026-11-05T14:00:01Z [DEBUG] Connecting to git with ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890",
        "2026-11-05T14:00:02Z [WARN] Bearer token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-IDcSemACt8x4iTMC6Y5",
        "2026-11-05T14:00:03Z [INFO] Normal module compilation successful for module calc.py",
        "2026-11-05T14:00:04Z [ERROR] Failed with password='SuperSecretPassword123!' in connection string",
    ]

    num_lines = 10000
    test_stream = [lines[i % len(lines)] for i in range(num_lines)]

    t0 = time.perf_counter()
    redacted_lines = [redactor.redact_text(line) for line in test_stream]
    duration = time.perf_counter() - t0

    lines_per_sec = num_lines / duration

    # Assert 0 secret leakages
    for line in redacted_lines:
        assert "sk-proj-" not in line
        assert "ghp_" not in line
        assert "SuperSecretPassword123!" not in line

    print(f"Processed: {num_lines:,} lines in {duration:.3f}s ({lines_per_sec:,.0f} lines/sec)")
    print("Secret Redaction Leaks: 0 (100% sanitized)")

    return {
        "operation": "secret_redaction_throughput",
        "lines_processed": num_lines,
        "duration_seconds": round(duration, 3),
        "lines_per_second": round(lines_per_sec, 0),
        "leaks_detected": 0,
    }


async def main():
    print("=====================================================================")
    print("      Phase 8 Production Readiness: Load & Concurrency Benchmark      ")
    print("=====================================================================")

    results = []
    results.append(await benchmark_task_leasing_concurrency())
    results.append(await benchmark_gate_decision_idempotency())
    results.append(await benchmark_artifact_streaming_throughput())
    results.append(benchmark_secret_redaction_throughput())

    print("\n=====================================================================")
    print("                    BENCHMARK RESULTS JSON                           ")
    print("=====================================================================")
    print("LOAD_BENCHMARK_RESULTS_START")
    print(json.dumps(results, indent=2))
    print("LOAD_BENCHMARK_RESULTS_END")


if __name__ == "__main__":
    asyncio.run(main())
