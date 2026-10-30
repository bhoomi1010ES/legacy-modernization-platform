"""Independent deterministic review findings, bound to exact changeset evidence."""

import ast
import logging
import re
from typing import Literal
from app.schemas.phase6 import Finding
from app.services.phase5_engine import digest
from app.services.secret_redactor import get_secret_redactor

logger = logging.getLogger(__name__)


def review(
    files: dict[str, str],
    contracts: list[dict],
    evidence_hash: str,
    *,
    design_notes: str = "",
    execution: dict | None = None,
) -> dict:
    try:
        findings = []
        for path, source in files.items():
            rules: list[
                tuple[str, Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"], str, str]
            ] = [
                (
                    r"\beval\s*\(|\bexec\s*\(|\bos\.system\s*\(|shell\s*=\s*True",
                    "CRITICAL",
                    "UNSAFE_EXECUTION",
                    "Dynamic execution or shell execution requires removal",
                ),
                (
                    r"(?i)(password|api_key|secret)\s*[:=]\s*['\"][^'\"]+",
                    "HIGH",
                    "SECRET",
                    "Potential embedded credential",
                ),
                (
                    r"(?i)\b(TODO|FIXME|NotImplementedError)\b",
                    "MEDIUM",
                    "INCOMPLETE",
                    "Unimplemented behavior requires human review",
                ),
                (
                    r"(?i)(SELECT|UPDATE|DELETE).*\+",
                    "HIGH",
                    "SQL_INJECTION",
                    "Concatenated SQL requires parameterization",
                ),
            ]
            for pattern, severity, category, message in rules:
                for match in re.finditer(pattern, source):
                    findings.append(
                        Finding(
                            finding_id=digest(
                                [path, category, match.start(), evidence_hash]
                            )[:24],
                            severity=severity,
                            category=category,
                            message=message,
                            path=path,
                            line=source[: match.start()].count("\n") + 1,
                            evidence_ref=evidence_hash,
                        ).model_dump()
                    )
            if path.endswith(".py"):
                try:
                    tree = ast.parse(source.replace('\x00', ''))
                    for node in ast.walk(tree):
                        if (
                            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and len(node.body) == 1
                            and isinstance(node.body[0], ast.Pass)
                        ):
                            findings.append(
                                Finding(
                                    finding_id=digest(
                                        [path, node.lineno, evidence_hash]
                                    )[:24],
                                    severity="HIGH",
                                    category="STUB",
                                    message="Public implementation is a stub",
                                    path=path,
                                    line=node.lineno,
                                    evidence_ref=evidence_hash,
                                ).model_dump()
                            )
                except SyntaxError:
                    findings.append(
                        Finding(
                            finding_id=digest([path, "syntax", evidence_hash])[:24],
                            severity="HIGH",
                            category="SYNTAX",
                            message="Generated Python cannot be parsed",
                            path=path,
                            evidence_ref=evidence_hash,
                        ).model_dump()
                    )
            if get_secret_redactor().redact_text(source) != source:
                findings.append(
                    Finding(
                        finding_id=digest([path, "secret", evidence_hash])[:24],
                        severity="CRITICAL",
                        category="SECRET",
                        message="Secret pattern detected",
                        path=path,
                        evidence_ref=evidence_hash,
                    ).model_dump()
                )
        combined = "\n".join(files.values())
        for contract in contracts:
            symbol = contract.get("symbol")
            if (
                symbol
                and re.fullmatch(r"[A-Za-z_]\w*", symbol)
                and not re.search(r"\b" + re.escape(symbol) + r"\b", combined)
            ):
                findings.append(
                    Finding(
                        finding_id=digest([symbol, evidence_hash])[:24],
                        severity="HIGH",
                        category="CONTRACT",
                        message=f"Required public symbol {symbol} is missing",
                        evidence_ref=evidence_hash,
                    ).model_dump()
                )
        if re.search(
            r"(?i)all tests pass|100%.*coverage|production.ready|self.verified",
            design_notes,
        ):
            findings.append(
                Finding(
                    finding_id=digest(["unsupported-claim", evidence_hash])[:24],
                    severity="MEDIUM",
                    category="UNSUPPORTED_CLAIM",
                    message="CodeWriter cannot certify execution, coverage or production readiness",
                    evidence_ref=evidence_hash,
                ).model_dump()
            )
        if execution is not None:
            failed = [
                item
                for item in execution.get("checks", [])
                if item.get("status") != "PASS"
            ]
            complete = (
                execution.get("available") is True
                and execution.get("passed") is True
                and {"build", "unit", "static", "security"}
                <= {item.get("category") for item in execution.get("checks", [])}
                and bool(execution.get("cases"))
                and all(
                    item.get("status") == "PASS" for item in execution.get("cases", [])
                )
                and not execution.get("unobserved_cases")
            )
            if not complete:
                findings.append(
                    Finding(
                        finding_id=digest(["execution-evidence", evidence_hash])[:24],
                        severity="HIGH",
                        category="EXECUTION_EVIDENCE",
                        message="Independent execution is missing, failing or includes unobserved required cases",
                        evidence_ref=execution.get("artifact_hash") or evidence_hash,
                    ).model_dump()
                )
            for item in failed:
                findings.append(
                    Finding(
                        finding_id=digest(
                            [item.get("category"), item.get("command"), evidence_hash]
                        )[:24],
                        severity="HIGH",
                        category="CHECK_" + item.get("category", "unknown").upper(),
                        message="Independent check failed; inspect referenced command stdout/stderr and exit code",
                        evidence_ref=item.get("artifact_hash") or evidence_hash,
                    ).model_dump()
                )
        return {
            "status": "REJECTED" if findings else "PASS",
            "findings": findings,
            "evidence_hash": evidence_hash,
            "reviewer_version": "deterministic-review-v6.2",
            "execution_evidence_hash": (
                execution.get("artifact_hash") if execution is not None else None
            ),
            "limitations": [
                "Static review plus tested behavior only; no claim of proof for untested semantics"
            ],
        }
    except Exception:
        logger.exception("phase6.review failed")
        raise
