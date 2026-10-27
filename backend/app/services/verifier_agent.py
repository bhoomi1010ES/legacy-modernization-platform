"""Independent verifier; missing execution can never produce PASS."""

import logging
from enum import Enum
from dataclasses import dataclass
from app.services import phase6_sandbox

logger = logging.getLogger(__name__)


class VerificationVerdict(str, Enum):
    # Verdict enum, not a password.
    PASS = "PASS"  # nosec B105
    RETRY = "RETRY"
    REPAIR = "REPAIR"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


@dataclass
class VerificationResult:
    module_id: object
    verdict: VerificationVerdict
    issues: list
    is_repairable: bool
    test_results_summary: dict
    artifact_id: object = None
    content_hash: str | None = None


class VerifierService:
    async def execute(self, files, cases, baseline_hash):
        try:
            return await phase6_sandbox.execute(files, cases, baseline_hash)
        except Exception:
            logger.exception("Verifier.execute failed")
            raise

    async def verify_module(
        self, db, job, module, *, user=None, force_failure=False, correlation_id=None
    ):
        """Read previously executed evidence; never trust artifact presence as execution."""
        try:
            from app.services.phase6_service import newest, detail

            attempt = await newest(db, module.module_id)
            info = await detail(db, attempt) if attempt else {"evidence": {}}
            evidence = info["evidence"]
            passed = (
                not force_failure
                and attempt is not None
                and attempt.status == "VERIFIED"
                and evidence.get("verification", {}).get("passed") is True
            )
            return VerificationResult(
                module.module_id,
                VerificationVerdict.PASS if passed else VerificationVerdict.REJECT,
                (
                    []
                    if passed
                    else [
                        {
                            "message": "Independent verification/review evidence is absent or failing"
                        }
                    ]
                ),
                False,
                evidence.get("verification", {}),
            )
        except Exception:
            logger.exception("Verifier.verify_module failed")
            raise


verifier_service = VerifierService()
