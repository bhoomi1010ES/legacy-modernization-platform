"""Deterministic golden comparison, isolated replay, and data proposal validation."""

import asyncio
import copy
import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import uuid
from datetime import datetime
from time import monotonic
from typing import Any
from pathlib import Path

from app.schemas.phase5 import NormalizationRule, Scenario, Table, ValidationRequest

logger = logging.getLogger(__name__)


class SchemaDiscoveryResult(tuple):
    """Dual-mode tuple to allow unpacking as (tables, notes) while preserving findings attribute."""
    def __new__(cls, tables, notes, findings=None):
        return super().__new__(cls, (tables, notes))

    def __init__(self, tables, notes, findings=None):
        self.tables = tables
        self.notes = notes
        self.findings = findings or []


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    except Exception:
        logger.exception("phase5.canonical failed")
        raise


def digest(value: Any) -> str:
    try:
        return hashlib.sha256(canonical(value)).hexdigest()
    except Exception:
        logger.exception("phase5.digest failed")
        raise


def normalize(value: Any, rules: list[NormalizationRule]) -> Any:
    """Normalize exact JSON pointers only; missing paths and unjustified sorts fail closed."""
    try:
        result = copy.deepcopy(value)
        for rule in rules:
            parts = [
                p.replace("~1", "/").replace("~0", "~")
                for p in rule.path[1:].split("/")
            ]
            parent = result
            for part in parts[:-1]:
                parent = parent[pointer_key(parent, part)]
            key = pointer_key(parent, parts[-1])
            item = parent[key]
            if rule.kind == "unordered":
                if not rule.contract_allows or not isinstance(item, list):
                    raise ValueError(
                        "Ordering can only be normalized for an explicitly unordered contract"
                    )
                parent[key] = sorted(item, key=canonical)
            elif rule.kind in ("random_id", "uuid"):
                pattern = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
                if not isinstance(item, str) or not re.fullmatch(pattern, item):
                    raise ValueError(
                        "Nondeterministic field does not match its declared type"
                    )
                parent[key] = f"<{rule.kind}>"
            elif rule.kind == "timestamp":
                pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"
                if not isinstance(item, str) or not re.fullmatch(pattern, item):
                    raise ValueError(
                        "Nondeterministic field does not match its declared type"
                    )
                datetime.fromisoformat(item.replace("Z", "+00:00"))
                parent[key] = "<timestamp>"
            elif rule.kind == "path":
                if not isinstance(item, str):
                    raise ValueError("Path normalization requires string value")
                normalized_path = re.sub(
                    r"(?:/tmp|/var/folders|C:\\Users\\[^\\]+\\AppData\\Local\\Temp|[A-Za-z]:\\[^ \t\r\n\v\f'\"`]+\\temp)/[^\s'\"`]+",
                    "<temp-path>",
                    item,
                    flags=re.IGNORECASE,
                )
                parent[key] = normalized_path if normalized_path != item else "<path>"
            elif rule.kind == "regex":
                if not rule.pattern:
                    raise ValueError("Regex normalization requires a declared pattern")
                if not isinstance(item, str) or not re.fullmatch(rule.pattern, item):
                    raise ValueError("Field does not match declared regex normalization pattern")
                parent[key] = rule.replacement or "<normalized>"
            else:
                pattern = (
                    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"
                    if rule.kind == "timestamp"
                    else r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
                )
                if not isinstance(item, str) or not re.fullmatch(pattern, item):
                    raise ValueError(
                        "Nondeterministic field does not match its declared type"
                    )
                parent[key] = f"<{rule.kind}>"
        return result
    except Exception:
        logger.exception("phase5.normalize failed")
        raise


def pointer_key(parent: Any, part: str) -> str | int:
    try:
        if isinstance(parent, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", part):
                raise ValueError(
                    "JSON pointers require a nonnegative canonical array index"
                )
            return int(part)
        if not isinstance(parent, dict):
            raise ValueError("JSON pointer traverses a scalar")
        return part
    except Exception:
        logger.exception("phase5.pointer_key failed")
        raise


async def replay(scenario: Scenario) -> dict:
    """Execute only the configured adapter with a strict evidence contract and resource bounds."""
    process = None
    container_name = f"phase5-{uuid.uuid4().hex}"
    t0 = monotonic()
    try:
        from app.core.config import settings

        image = os.getenv("PHASE5_LEGACY_IMAGE", settings.PHASE5_LEGACY_IMAGE).strip()
        raw_command = os.getenv(
            "PHASE5_LEGACY_COMMAND_JSON", settings.PHASE5_LEGACY_COMMAND_JSON
        )
        if not image or not raw_command:
            return {
                "available": False,
                "execution_mode": "UNAVAILABLE",
                "duration_ms": int((monotonic() - t0) * 1000),
                "exit_status": None,
                "reason": "ADAPTER_NOT_CONFIGURED: PHASE5_LEGACY_IMAGE and PHASE5_LEGACY_COMMAND_JSON are required",
            }
        try:
            command = json.loads(raw_command)
        except (ValueError, TypeError):
            return {
                "available": False,
                "execution_mode": "UNAVAILABLE",
                "duration_ms": int((monotonic() - t0) * 1000),
                "exit_status": None,
                "reason": "INVALID_ADAPTER_CONFIG: command must be a JSON argv array",
            }
        if (
            not re.fullmatch(r"[A-Za-z0-9./:_@-]+", image)
            or image.startswith("-")
            or not isinstance(command, list)
            or not command
            or not all(isinstance(c, str) and c for c in command)
        ):
            return {
                "available": False,
                "execution_mode": "UNAVAILABLE",
                "duration_ms": int((monotonic() - t0) * 1000),
                "exit_status": None,
                "reason": "INVALID_ADAPTER_CONFIG: invalid image or command argv",
            }
        process = await asyncio.create_subprocess_exec(
            "docker",
            "run",
            "--name",
            container_name,
            "--rm",
            "--pull=never",
            "--network=none",
            "--read-only",
            "--memory=256m",
            "--cpus=1",
            "--pids-limit=64",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user=65534:65534",
            "--log-driver=none",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=32m",
            "-i",
            image,
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=1048576,
        )
        output, error = await asyncio.wait_for(
            adapter_exchange(
                process,
                canonical({"scenario": scenario.name, "inputs": scenario.inputs}),
            ),
            timeout=30,
        )
        duration_ms = int((monotonic() - t0) * 1000)
        stdout_sample = output[:2000].decode("utf-8", errors="replace")
        stderr_sample = error[:2000].decode("utf-8", errors="replace")
        if process.returncode:
            diagnostic = error.decode("utf-8", errors="replace").lower()
            if any(
                t in diagnostic
                for t in (
                    "daemon",
                    "docker_engine",
                    "dockerdesktoplinuxengine",
                    "cannot connect",
                    "failed to connect",
                )
            ):
                reason = "DOCKER_UNAVAILABLE: Docker daemon socket is not reachable"
            elif any(
                t in diagnostic
                for t in ("no such image", "unable to find image", "pull access denied")
            ):
                reason = "IMAGE_UNAVAILABLE: configured image is not present locally; pulling is prohibited"
            else:
                reason = f"ADAPTER_EXIT: legacy sandbox exited with code {process.returncode}"
            return {
                "available": False,
                "execution_mode": "UNAVAILABLE",
                "duration_ms": duration_ms,
                "exit_status": process.returncode,
                "stdout_sample": stdout_sample,
                "stderr_sample": stderr_sample,
                "reason": reason,
            }
        data = json.loads(
            output,
            object_pairs_hook=strict_adapter_object,
            parse_constant=reject_json_constant,
        )
        if not isinstance(data, dict) or set(data) != {"output", "side_effects"}:
            return {
                "available": False,
                "execution_mode": "REAL_CONTAINER",
                "duration_ms": duration_ms,
                "exit_status": process.returncode,
                "stdout_sample": stdout_sample,
                "stderr_sample": stderr_sample,
                "reason": "INVALID_ADAPTER_EVIDENCE: stdout must contain exactly output and side_effects",
            }
        # Comparison uses original observations; redaction occurs before persistence, not before pass/fail.
        return {
            "available": True,
            "execution_mode": "REAL_CONTAINER",
            "duration_ms": duration_ms,
            "exit_status": process.returncode,
            "container_name": container_name,
            "stdout_sample": stdout_sample,
            "stderr_sample": stderr_sample,
            **data,
        }
    except FileNotFoundError:
        logger.exception("phase5.replay Docker executable unavailable")
        return {
            "available": False,
            "execution_mode": "UNAVAILABLE",
            "duration_ms": int((monotonic() - t0) * 1000),
            "exit_status": None,
            "reason": "DOCKER_NOT_INSTALLED: Docker executable was not found",
        }
    except asyncio.TimeoutError:
        logger.exception("phase5.replay timed out")
        return {
            "available": False,
            "execution_mode": "REAL_CONTAINER",
            "duration_ms": int((monotonic() - t0) * 1000),
            "exit_status": None,
            "reason": "ADAPTER_TIMEOUT: 30 second execution deadline exceeded",
        }
    except (ValueError, UnicodeError):
        logger.exception("phase5.replay invalid or oversized evidence")
        return {
            "available": False,
            "execution_mode": "REAL_CONTAINER",
            "duration_ms": int((monotonic() - t0) * 1000),
            "exit_status": process.returncode if process else None,
            "reason": "INVALID_ADAPTER_EVIDENCE: malformed JSON, duplicate keys, nonfinite values or output limit exceeded",
        }
    except Exception:
        logger.exception("phase5.replay infrastructure failure")
        return {
            "available": False,
            "execution_mode": "UNAVAILABLE",
            "duration_ms": int((monotonic() - t0) * 1000),
            "exit_status": None,
            "reason": "SANDBOX_ERROR: legacy adapter could not be executed",
        }
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
            try:
                cleanup = await asyncio.create_subprocess_exec(
                    "docker",
                    "rm",
                    "--force",
                    container_name,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(cleanup.wait(), timeout=10)
            except Exception:
                logger.exception(
                    "phase5 sandbox cleanup failed | container=%s", container_name
                )


async def adapter_exchange(process, payload: bytes) -> tuple[bytes, bytes]:
    """The outer execution deadline includes stdin backpressure and both output streams."""
    try:

        async def send() -> None:
            try:
                process.stdin.write(payload)
                await process.stdin.drain()
                process.stdin.close()
            except Exception:
                logger.exception("phase5.adapter_exchange stdin failed")
                raise

        _, output, error, _ = await asyncio.gather(
            send(),
            read_bounded(process.stdout),
            read_bounded(process.stderr),
            process.wait(),
        )
        return output, error
    except Exception:
        logger.exception("phase5.adapter_exchange failed")
        raise


def strict_adapter_object(pairs: list) -> dict:
    try:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate adapter JSON key")
            result[key] = value
        return result
    except Exception:
        logger.exception("phase5.strict_adapter_object failed")
        raise


def reject_json_constant(value: str):
    try:
        raise ValueError("Nonfinite adapter JSON values are prohibited")
    except Exception:
        logger.exception("phase5.reject_json_constant failed")
        raise


async def read_bounded(stream: asyncio.StreamReader) -> bytes:
    try:
        chunks = bytearray()
        while True:
            chunk = await stream.read(65536)
            if not chunk:
                return bytes(chunks)
            chunks.extend(chunk)
            if len(chunks) > 1048576:
                raise ValueError("Legacy adapter output exceeds 1 MiB")
    except Exception:
        logger.exception("phase5.read_bounded failed")
        raise


def coverage(modules: list[str], interfaces: list[str], cases: list[dict]) -> dict:
    try:

        def entry(name: str, matching: list[dict]) -> dict:
            try:
                statuses = {c["outcome"] for c in matching}
                status = next(
                    (
                        v
                        for v in ("NON_REPRODUCIBLE", "FAILED", "UNAVAILABLE", "PASSED")
                        if v in statuses
                    ),
                    "UNTESTED",
                )
                return {
                    "name": name,
                    "covered": bool(matching) and statuses == {"PASSED"},
                    "status": {"PASSED": "PASS", "FAILED": "FAIL"}.get(status, status),
                    "observed": any(c["outcome"] != "UNAVAILABLE" for c in matching),
                }
            except Exception:
                logger.exception("phase5.coverage.entry failed")
                raise

        module_rows = [
            entry(m, [c for c in cases if c["module"] == m])
            for m in sorted(set(modules) | {c["module"] for c in cases})
        ]
        interface_rows = [
            entry(i, [c for c in cases if c["interface"] == i])
            for i in sorted(set(interfaces) | {c["interface"] for c in cases})
        ]
        behaviors = [entry(c["behavior"], [c]) for c in cases]
        rows = module_rows + interface_rows + behaviors
        return {
            "modules": module_rows,
            "interfaces": interface_rows,
            "behaviors": behaviors,
            "executed_behaviors": [
                c["behavior"] for c in cases if c["outcome"] != "UNAVAILABLE"
            ],
            "untested_paths": [r["name"] for r in rows if not r["covered"]],
            "percent": (
                round(100 * sum(r["covered"] for r in rows) / len(rows), 2)
                if rows
                else 0
            ),
            "limitations": [
                "Scenario coverage is not line or branch coverage; unobserved paths remain unverified"
            ],
        }
    except Exception:
        logger.exception("phase5.coverage failed")
        raise


def migration_plan(
    source: list[Table], target: list[Table], findings: list[dict] = None
) -> dict:
    """Generate a restricted SQLite test proposal; other dialects require reviewed adapters."""
    try:
        target = target or source
        review_issues = []
        findings = findings or []
        for f in findings:
            if f.get("status") in ("REVIEW_REQUIRED", "UNSUPPORTED", "BLOCKED"):
                review_issues.append(
                    f"Complex/proprietary construct ({f.get('construct')}: {f.get('name')}) requires review: {f.get('reason')}"
                )
        for tables in (source, target):
            if len({t.name for t in tables}) != len(tables):
                raise ValueError("Duplicate table name")
            for table in tables:
                if len({c.name for c in table.columns}) != len(table.columns):
                    raise ValueError("Duplicate column name")
                if sum(c.primary_key for c in table.columns) > 1:
                    review_issues.append(
                        "Composite keys require a reviewed dialect adapter"
                    )
                for column in table.columns:
                    if bool(column.references_table) != bool(column.references_column):
                        raise ValueError(
                            "Both referenced table and column are required"
                        )
                    if column.references_table:
                        referenced = next(
                            (t for t in tables if t.name == column.references_table),
                            None,
                        )
                        parent = (
                            next(
                                (
                                    c
                                    for c in referenced.columns
                                    if c.name == column.references_column
                                ),
                                None,
                            )
                            if referenced
                            else None
                        )
                        if parent is None or not (parent.primary_key or parent.unique):
                            raise ValueError(
                                "Foreign keys must reference an inventoried primary or unique key"
                            )
        statements, mappings, differences = [], [], []
        sources = {t.name: t for t in source}
        for table in target:
            definitions = []
            original = (
                {c.name: c for c in sources[table.name].columns}
                if table.name in sources
                else {}
            )
            for col in table.columns:
                sql = f'"{col.name}" {col.type}'
                sql += " PRIMARY KEY" if col.primary_key else ""
                sql += " NOT NULL" if not col.nullable else ""
                sql += " UNIQUE" if col.unique else ""
                if col.max_length:
                    sql += f' CHECK(length("{col.name}") <= {col.max_length})'
                if col.references_table:
                    sql += f' REFERENCES "{col.references_table}"("{col.references_column}") DEFERRABLE INITIALLY DEFERRED'
                definitions.append(sql)
                mappings.append(
                    {
                        "table": table.name,
                        "source": col.name if col.name in original else None,
                        "target": col.name,
                        "type": col.type,
                        "rule": "identity; no implicit casts or truncation",
                    }
                )
                if (
                    col.name not in original
                    or original[col.name].model_dump() != col.model_dump()
                ):
                    differences.append(
                        {
                            "table": table.name,
                            "column": col.name,
                            "source": (
                                original[col.name].model_dump()
                                if col.name in original
                                else None
                            ),
                            "target": col.model_dump(),
                        }
                    )
            statements.append(
                f'CREATE TABLE "{table.name}" (' + ", ".join(definitions) + ");"
            )
        for table in source:
            current = next((t for t in target if t.name == table.name), None)
            for col in table.columns:
                if current is None or col.name not in {c.name for c in current.columns}:
                    differences.append(
                        {
                            "table": table.name,
                            "column": col.name,
                            "source": col.model_dump(),
                            "target": None,
                        }
                    )
        return {
            "scope": "disposable",
            "status": (
                "REVIEW_REQUIRED"
                if review_issues
                else "READY" if source else "NOT_APPLICABLE"
            ),
            "review_reasons": review_issues,
            "assumptions": [
                "Identity mappings only; unsupported source semantics require explicit reviewed schema overrides"
            ],
            "dialect": "sqlite",
            "source_tables": [t.model_dump() for t in source],
            "tables": [t.model_dump() for t in target],
            "mappings": mappings,
            "differences": differences,
            "schema_findings": findings,
            "upgrade_sql": "" if review_issues else "\n".join(statements),
            "rollback_sql": "\n".join(
                f'DROP TABLE "{t.name}";' for t in reversed(target)
            ),
            # Identifiers are restricted by Table.name; sample values are always parameters.
            "validation_queries": [
                f'SELECT COUNT(*) FROM "{t.name}";' for t in target  # nosec B608
            ]
            + ["PRAGMA foreign_key_check;", "PRAGMA integrity_check;"],
            "risks": [
                "Disposable SQLite validation only; production dialect semantics, triggers and stored procedures require review",
                "Rollback discards disposable target data; source snapshot is retained",
            ],
            "limitations": (
                []
                if source
                else ["No structured source schema supplied; inventory requires review"]
            ),
        }
    except Exception:
        logger.exception("phase5.migration_plan failed")
        raise


def discover_schema(job_id: str, paths: list[str]) -> SchemaDiscoveryResult:
    """Inspect ordinary CREATE TABLE DDL and complex/proprietary constructs in staged workspace."""
    connection = None
    try:
        backend = Path(__file__).resolve().parents[2]
        roots = [
            backend / "repo_workspaces" / f"job_{job_id}",
            backend / "repo_workspaces" / f"job_{job_id}_git",
            backend.parent / "repo_workspaces" / f"job_{job_id}",
        ]
        root = next((p.resolve() for p in roots if p.is_dir()), None)
        if root is None:
            return SchemaDiscoveryResult([], ["Staged workspace unavailable for DDL discovery"], [])
        connection = sqlite3.connect(":memory:")
        notes = []
        findings = []
        for relative in paths[:100]:
            path = (root / relative).resolve()
            if (
                root not in path.parents
                or not path.is_file()
                or path.suffix.lower() != ".sql"
                or path.stat().st_size > 262144
            ):
                notes.append("Unsupported or unsafe schema evidence path")
                findings.append({
                    "construct": "file",
                    "name": relative,
                    "status": "UNSUPPORTED",
                    "reason": "Unsupported or unsafe schema evidence path",
                    "file": relative,
                })
                continue
            for statement in path.read_text(encoding="utf-8", errors="replace").split(
                ";"
            )[:200]:
                cleaned = re.sub(r"--[^\n]*", "", statement).strip()
                if not cleaned:
                    continue

                # Check for triggers
                trig_match = re.search(
                    r'CREATE\s+TRIGGER\s+(?:IF\s+NOT\s+EXISTS\s+)?["`\[]?([A-Za-z_][A-Za-z0-9_]*)["`\]]?',
                    cleaned,
                    re.I,
                )
                if trig_match:
                    name = trig_match.group(1)
                    notes.append(f"Database trigger {name} in {relative} requires manual review")
                    findings.append({
                        "construct": "trigger",
                        "name": name,
                        "status": "REVIEW_REQUIRED",
                        "reason": "Database trigger requires manual dialect-specific logic verification",
                        "file": relative,
                        "raw_sql": cleaned[:200],
                    })
                    continue

                # Check for procedures
                proc_match = re.search(
                    r'CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+["`\[]?([A-Za-z_][A-Za-z0-9_]*)["`\]]?',
                    cleaned,
                    re.I,
                )
                if proc_match:
                    name = proc_match.group(1)
                    notes.append(f"Stored procedure {name} in {relative} requires manual review")
                    findings.append({
                        "construct": "procedure",
                        "name": name,
                        "status": "REVIEW_REQUIRED",
                        "reason": "Stored procedures are dialect-specific and cannot be validated in disposable SQLite",
                        "file": relative,
                        "raw_sql": cleaned[:200],
                    })
                    continue

                # Check for functions
                func_match = re.search(
                    r'CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+["`\[]?([A-Za-z_][A-Za-z0-9_]*)["`\]]?',
                    cleaned,
                    re.I,
                )
                if func_match:
                    name = func_match.group(1)
                    notes.append(f"Database function {name} in {relative} requires manual review")
                    findings.append({
                        "construct": "function",
                        "name": name,
                        "status": "REVIEW_REQUIRED",
                        "reason": "Database functions require target dialect runtime",
                        "file": relative,
                        "raw_sql": cleaned[:200],
                    })
                    continue

                # Check for views
                view_match = re.search(
                    r'CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+["`\[]?([A-Za-z_][A-Za-z0-9_]*)["`\]]?',
                    cleaned,
                    re.I,
                )
                if view_match:
                    name = view_match.group(1)
                    notes.append(f"Database view {name} in {relative} requires manual review")
                    findings.append({
                        "construct": "view",
                        "name": name,
                        "status": "REVIEW_REQUIRED",
                        "reason": "Database views require target dialect semantic review",
                        "file": relative,
                        "raw_sql": cleaned[:200],
                    })
                    continue

                # Check for sequences
                seq_match = re.search(
                    r'CREATE\s+SEQUENCE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`\[]?([A-Za-z_][A-Za-z0-9_]*)["`\]]?',
                    cleaned,
                    re.I,
                )
                if seq_match:
                    name = seq_match.group(1)
                    notes.append(f"Sequence {name} in {relative} requires manual review")
                    findings.append({
                        "construct": "sequence",
                        "name": name,
                        "status": "REVIEW_REQUIRED",
                        "reason": "Sequence definition requires target dialect sequence engine",
                        "file": relative,
                        "raw_sql": cleaned[:200],
                    })
                    continue

                # Check for indexes
                idx_match = re.search(
                    r'CREATE\s+(UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?["`\[]?([A-Za-z_][A-Za-z0-9_]*)["`\]]?\s+ON\s+["`\[]?([A-Za-z_][A-Za-z0-9_]*)["`\]]?\s*\(([^)]+)\)',
                    cleaned,
                    re.I,
                )
                if idx_match:
                    is_unique = bool(idx_match.group(1))
                    idx_name = idx_match.group(2)
                    target_tbl = idx_match.group(3)
                    cols = [c.strip() for c in idx_match.group(4).split(",")]
                    is_composite = len(cols) > 1
                    try:
                        connection.execute(cleaned)
                    except sqlite3.Error:
                        pass
                    if is_composite:
                        notes.append(
                            f"Composite uniqueness on {target_tbl} requires manual review"
                            if is_unique
                            else f"Composite index on {target_tbl} requires manual review"
                        )
                        findings.append({
                            "construct": "composite_constraint",
                            "name": idx_name,
                            "status": "REVIEW_REQUIRED",
                            "reason": f"Composite {'unique ' if is_unique else ''}index on {target_tbl} requires manual review",
                            "file": relative,
                            "raw_sql": cleaned[:200],
                        })
                    else:
                        findings.append({
                            "construct": "index",
                            "name": idx_name,
                            "status": "SUPPORTED",
                            "reason": "Single-column index supported",
                            "file": relative,
                            "raw_sql": cleaned[:200],
                        })
                    continue

                # Allow only bounded ordinary table definitions, with no query or procedural clauses.
                match = re.fullmatch(
                    r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`\[]?([A-Za-z_][A-Za-z0-9_]*)["`\]]?\s*\([\s\S]*\)',
                    cleaned,
                    re.I,
                )
                if not match or re.search(
                    r"\b(SELECT|ATTACH|PRAGMA|LOAD_EXTENSION)\b",
                    cleaned,
                    re.I,
                ):
                    if cleaned:
                        notes.append(
                            f"Unparsed DDL in {relative}; manual dialect review required"
                        )
                        findings.append({
                            "construct": "sql_statement",
                            "name": cleaned[:30],
                            "status": "REVIEW_REQUIRED",
                            "reason": f"Unparsed DDL in {relative}; manual dialect review required",
                            "file": relative,
                            "raw_sql": cleaned[:200],
                        })
                    continue
                try:
                    connection.execute(cleaned)
                    tbl_name = match.group(1)
                    findings.append({
                        "construct": "table",
                        "name": tbl_name,
                        "status": "SUPPORTED",
                        "reason": "Parsed and created in validation SQLite engine",
                        "file": relative,
                        "raw_sql": cleaned[:200],
                    })
                    if re.search(
                        r"\b(CHECK|DEFAULT|COLLATE|GENERATED|WITHOUT\s+ROWID)\b",
                        cleaned,
                        re.I,
                    ):
                        notes.append(
                            f"Unsupported CHECK/default/collation/generated semantics in {relative}; review required"
                        )
                        findings.append({
                            "construct": "constraint",
                            "name": f"{tbl_name}_advanced_semantics",
                            "status": "REVIEW_REQUIRED",
                            "reason": "Unsupported CHECK/default/collation/generated semantics; review required",
                            "file": relative,
                            "raw_sql": cleaned[:200],
                        })
                except sqlite3.Error as err:
                    tbl_name = match.group(1) if match else "unknown"
                    notes.append(
                        f"Unsupported DDL in {relative}; manual dialect review required"
                    )
                    findings.append({
                        "construct": "table",
                        "name": tbl_name,
                        "status": "REVIEW_REQUIRED",
                        "reason": f"SQLite execution failed: {err}",
                        "file": relative,
                        "raw_sql": cleaned[:200],
                    })
        tables = []
        for (name,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", name):
                continue
            foreign = {
                r[3]: (r[2], r[4])
                for r in connection.execute(f'PRAGMA foreign_key_list("{name}")')
            }
            unique = set()
            for index in connection.execute(f'PRAGMA index_list("{name}")').fetchall():
                if index[2] and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", index[1]):
                    cols = connection.execute(
                        f'PRAGMA index_info("{index[1]}")'
                    ).fetchall()
                    if len(cols) == 1:
                        unique.add(cols[0][2])
                    else:
                        notes.append(
                            f"Composite uniqueness on {name} requires manual review"
                        )
                        findings.append({
                            "construct": "composite_constraint",
                            "name": f"{name}_composite_unique",
                            "status": "REVIEW_REQUIRED",
                            "reason": f"Composite uniqueness on {name} requires manual review",
                        })
            columns = []
            for row in connection.execute(f'PRAGMA table_info("{name}")'):
                raw_type = row[2].upper()
                kind = (
                    "INTEGER"
                    if "INT" in raw_type
                    else (
                        "REAL"
                        if any(t in raw_type for t in ("REAL", "FLOAT", "DOUBLE", "NUMERIC", "DECIMAL"))
                        else "BLOB" if raw_type == "BLOB" else "TEXT"
                    )
                )
                if raw_type not in ("INTEGER", "REAL", "TEXT", "BLOB"):
                    notes.append(
                        f"Type mapping assumption: {name}.{row[1]} {raw_type} -> {kind}; target dialect review required"
                    )
                    findings.append({
                        "construct": "data_type",
                        "name": f"{name}.{row[1]}",
                        "status": "REVIEW_REQUIRED",
                        "reason": f"Type mapping assumption: {name}.{row[1]} {raw_type} -> {kind}; target dialect review required",
                    })
                length = re.search(r"(?:VAR)?CHAR\((\d+)\)", raw_type)
                ref = foreign.get(row[1], (None, None))
                columns.append(
                    {
                        "name": row[1],
                        "type": kind,
                        "nullable": not bool(row[3] or row[5]),
                        "primary_key": bool(row[5]),
                        "unique": row[1] in unique,
                        "max_length": int(length[1]) if length else None,
                        "references_table": ref[0],
                        "references_column": ref[1],
                    }
                )
            try:
                tables.append(Table.model_validate({"name": name, "columns": columns}))
            except ValueError:
                notes.append(f"Unsupported identifiers or constraints on {name}")
                findings.append({
                    "construct": "table",
                    "name": name,
                    "status": "UNSUPPORTED",
                    "reason": f"Unsupported identifiers or constraints on {name}",
                })
        return SchemaDiscoveryResult(tables, sorted(set(notes)), findings)
    except Exception:
        logger.exception("phase5.discover_schema failed | job_id=%s", job_id)
        raise
    finally:
        if connection:
            connection.close()


def validate_migration(plan: dict, request: ValidationRequest) -> dict:
    """Construct and destroy an in-memory DB; never accepts URLs, paths or arbitrary SQL."""
    connection = None
    try:
        tables = [Table.model_validate(t) for t in plan["tables"]]
        safe_plan = migration_plan(
            [Table.model_validate(t) for t in plan["source_tables"]],
            tables,
            findings=plan.get("schema_findings"),
        )
        if safe_plan["status"] == "REVIEW_REQUIRED":
            return {
                "scope": "disposable",
                "status": "REVIEW_REQUIRED",
                "passed": False,
                "errors": [],
                "counts": {},
                "rollback_verified": False,
                "sample_data_provided": False,
                "review_required": True,
                "limitations": safe_plan["review_reasons"],
                "schema_findings": safe_plan.get("schema_findings", []),
            }
        connection = sqlite3.connect(":memory:")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(safe_plan["upgrade_sql"])
        names = {t.name for t in tables}
        if len({t.name for t in request.tables}) != len(request.tables) or any(
            t.name not in names for t in request.tables
        ):
            raise ValueError("Unknown or duplicate sample table")
        errors, counts = [], {}
        for table in tables:
            sample = next((s for s in request.tables if s.name == table.name), None)
            rows = sample.rows if sample else []
            columns = {c.name: c for c in table.columns}
            for index, row in enumerate(rows):
                if set(row) - set(columns):
                    errors.append(
                        {"table": table.name, "row": index, "issue": "Unknown columns"}
                    )
                    continue
                valid = True
                if any(
                    (not col.nullable or col.primary_key) and row.get(name) is None
                    for name, col in columns.items()
                ):
                    errors.append(
                        {
                            "table": table.name,
                            "row": index,
                            "issue": "Missing required or null key value",
                        }
                    )
                    continue
                for name, value in row.items():
                    expected = columns[name].type
                    if value is not None and (
                        (
                            expected == "INTEGER"
                            and (
                                type(value) is not int or not -(2**63) <= value < 2**63
                            )
                        )
                        or (
                            expected == "REAL"
                            and (type(value) is not float or not math.isfinite(value))
                        )
                        or (expected == "TEXT" and not isinstance(value, str))
                        or expected == "BLOB"
                    ):
                        valid = False
                if not valid:
                    errors.append(
                        {
                            "table": table.name,
                            "row": index,
                            "issue": "Type mismatch; implicit conversion refused",
                        }
                    )
                    continue
                try:
                    keys = list(row)
                    if keys:
                        quoted = ",".join(f'"{k}"' for k in keys)
                        connection.execute(
                            # Schema-validated identifiers; values are bound parameters.
                            f'INSERT INTO "{table.name}" ({quoted}) VALUES ({",".join("?" for _ in keys)})',  # nosec B608
                            [row[k] for k in keys],
                        )
                    else:
                        connection.execute(f'INSERT INTO "{table.name}" DEFAULT VALUES')
                except sqlite3.IntegrityError:
                    errors.append(
                        {
                            "table": table.name,
                            "row": index,
                            "issue": "Null, duplicate, truncation or constraint violation",
                        }
                    )
            count = connection.execute(
                # Table.name is a strict identifier; the database is :memory:.
                f'SELECT COUNT(*) FROM "{table.name}"'  # nosec B608
            ).fetchone()[0]
            counts[table.name] = {
                "source": len(rows),
                "target": count,
                "reconciled": count == len(rows),
            }
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            errors.append({"issue": "Referential integrity violation"})
        connection.rollback()
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.executescript(safe_plan["rollback_sql"])
        rollback_ok = not connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {
            "scope": "disposable",
            "status": (
                "REVIEW_REQUIRED"
                if plan.get("status") == "REVIEW_REQUIRED"
                else "PASS" if not errors and rollback_ok else "FAIL"
            ),
            "passed": not errors
            and rollback_ok
            and plan.get("status") != "REVIEW_REQUIRED",
            "errors": errors,
            "counts": counts,
            "rollback_verified": rollback_ok,
            "sample_data_provided": any(t.rows for t in request.tables),
            "review_required": plan.get("status") == "REVIEW_REQUIRED",
            "limitations": (
                ["Empty samples validate DDL only"]
                if not any(t.rows for t in request.tables)
                else []
            ),
        }
    except Exception:
        logger.exception("phase5.validate_migration failed")
        raise
    finally:
        if connection:
            connection.close()
