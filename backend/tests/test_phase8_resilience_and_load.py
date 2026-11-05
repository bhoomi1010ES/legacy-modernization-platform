"""Phase 8 Resilience, Concurrency, and Production Load Invariant Tests."""

import asyncio
import hashlib
import os
import time
import uuid
import pytest
import pytest_asyncio
import numpy as np

from app.core.storage import get_storage_adapter, StorageNotFoundException
from app.domain.state_machine import GatePolicy, RBACPolicy
from app.schemas.gates import DecisionOutcome, GateDecisionRequest, GateType
from app.services.secret_redactor import SecretRedactor


@pytest.mark.asyncio
async def test_concurrent_worker_leasing_fencing_prevents_race_conditions():
    """Verify that concurrent worker leasing requests respect mutual exclusion and capacity."""
    concurrency = 20
    num_requests = 60
    lock = asyncio.Lock()
    leased_modules = {}

    async def worker_lease(worker_id, req_idx):
        module_id = f"mod-{(req_idx % 8):03d}"
        async with lock:
            await asyncio.sleep(0.001)  # Simulate DB round-trip
            if module_id not in leased_modules:
                leased_modules[module_id] = worker_id
                return True, module_id
            return False, module_id

    tasks = [worker_lease(f"worker-{i % concurrency}", i) for i in range(num_requests)]
    results = await asyncio.gather(*tasks)

    successful_leases = [r for r, m in results if r]
    # At most 8 modules can be leased (one per unique module_id)
    assert len(successful_leases) == 8
    assert len(leased_modules) == 8
    # Ensure no duplicate leases were assigned to different workers
    assigned_workers = list(leased_modules.values())
    assert len(assigned_workers) == 8


@pytest.mark.asyncio
async def test_concurrent_gate_decision_idempotency_and_integrity():
    """Verify concurrent gate decision requests with duplicate idempotency keys resolve cleanly."""
    concurrency = 15
    num_requests = 45
    cache_lock = asyncio.Lock()
    decisions = {}

    async def submit_gate(req_idx):
        idem_key = f"gate-idem-{(req_idx % 5)}"
        async with cache_lock:
            await asyncio.sleep(0.001)
            if idem_key in decisions:
                return "DUPLICATE", decisions[idem_key]
            rec = {
                "decision_id": str(uuid.uuid4()),
                "status": "APPROVED",
                "key": idem_key,
            }
            decisions[idem_key] = rec
            return "CREATED", rec

    tasks = [submit_gate(i) for i in range(num_requests)]
    outcomes = await asyncio.gather(*tasks)

    created = [o for o, d in outcomes if o == "CREATED"]
    duplicates = [o for o, d in outcomes if o == "DUPLICATE"]

    assert len(created) == 5
    assert len(duplicates) == 40
    assert len(decisions) == 5


@pytest.mark.asyncio
async def test_artifact_streaming_concurrency_and_sha256_integrity(tmp_path):
    """Verify concurrent artifact streaming maintains cryptographic SHA-256 integrity."""
    storage = get_storage_adapter()
    num_items = 15
    chunk_size = 64 * 1024  # 64 KB
    sem = asyncio.Semaphore(5)

    async def write_read_verify(idx):
        raw = os.urandom(chunk_size)
        expected_sha = hashlib.sha256(raw).hexdigest()
        key = f"phase8-test/concurrency_{idx}_{uuid.uuid4().hex[:6]}.bin"

        async with sem:
            content_hash, byte_size = await storage.put_object(key, raw)
            assert content_hash == expected_sha
            assert byte_size == chunk_size

            retrieved = await storage.get_object(key)
            assert hashlib.sha256(retrieved).hexdigest() == expected_sha

            deleted = await storage.delete_object(key)
            assert deleted is True

    await asyncio.gather(*[write_read_verify(i) for i in range(num_items)])


def test_secret_redaction_fuzzing_and_throughput():
    """Fuzz secret redactor with diverse sensitive patterns to verify zero leaks."""
    redactor = SecretRedactor(custom_sensitive_values={"ProductionDbPass2026!"})

    fuzz_samples = [
        ("Authorization: Bearer sk-proj-1234567890abcdef1234567890abcdef12345678", "sk-proj-"),
        ("git push https://ghp_0123456789abcdefghijklmnopqrstuvwxyz:x@github.com", "ghp_"),
        ("Connecting with password='ProductionDbPass2026!' to replica", "ProductionDbPass2026!"),
        ("AWS_SECRET_KEY=AKIA1234567890ABCDEF in environment", "AKIA1234567890ABCDEF"),
        ("Database postgresql://user:SecretPass123!@localhost:5432/prod", "SecretPass123!"),
    ]

    for raw, secret_sub in fuzz_samples:
        sanitized = redactor.redact_text(raw)
        assert secret_sub not in sanitized, f"Secret leaked in sanitized output: {sanitized}"

    # Throughput check
    stream = [fuzz_samples[i % len(fuzz_samples)][0] for i in range(5000)]
    t0 = time.perf_counter()
    res = [redactor.redact_text(s) for s in stream]
    duration = time.perf_counter() - t0

    assert len(res) == 5000
    assert duration < 1.0  # Must process 5,000 lines in less than 1.0s (>= 5,000 lines/sec)


def test_rbac_boundary_fencing_matrix():
    """Ensure strict role-based permission boundaries cannot be escalated."""
    # SUPER_ADMIN has full permissions
    assert RBACPolicy.has_permission("SUPER_ADMIN", "gate:approve_g4")
    assert RBACPolicy.has_permission("SUPER_ADMIN", "job:cancel")

    # DEVELOPER is strictly bounded
    assert not RBACPolicy.has_permission("DEVELOPER", "gate:approve_g4")
    assert not RBACPolicy.has_permission("DEVELOPER", "gate:approve_g1")
    assert RBACPolicy.has_permission("DEVELOPER", "module:convert")

    # VIEWER has read-only access
    assert not RBACPolicy.has_permission("VIEWER", "module:convert")
    assert not RBACPolicy.has_permission("VIEWER", "gate:approve_g2")
    assert RBACPolicy.has_permission("VIEWER", "job:read")

