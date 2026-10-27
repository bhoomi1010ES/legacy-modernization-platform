"""Evidence collection, hashing, redaction, and verification service."""

import hashlib
import logging
from typing import Dict, List, Optional
import uuid

from app.schemas.phase4 import ConfidenceLevel, EvidenceRef, EvidenceType
from app.services.secret_redactor import get_secret_redactor

logger = logging.getLogger(__name__)


class EvidenceService:
    """Manages evidence collection, hashing, secret redaction, and evidence index generation."""

    def __init__(self):
        try:
            self.redactor = get_secret_redactor()
        except Exception as exc:
            logger.exception("EvidenceService init failed | %s: %s", type(exc).__name__, exc)
            raise

    def create_evidence(
        self,
        *,
        source_artifact: str,
        source_path: str,
        evidence_type: EvidenceType,
        source_location: Optional[str] = None,
        raw_excerpt: Optional[str] = None,
        evidence_excerpt: Optional[str] = None,
        confidence: ConfidenceLevel = ConfidenceLevel.CONFIRMED,
        agent_name: str = "analyzer",
        model_version: Optional[str] = None,
        artifact_version: int = 1,
    ) -> EvidenceRef:
        """Create a sanitized, hashed evidence reference."""
        try:
            raw_excerpt = raw_excerpt or evidence_excerpt
            sanitized_path = source_path.replace("\\", "/").strip()
            content_hash = None
            sanitized_excerpt = None

            if raw_excerpt:
                clean_text = self.redactor.redact_text(raw_excerpt)
                if len(clean_text) > 1000:
                    clean_text = clean_text[:1000] + "... [TRUNCATED]"
                sanitized_excerpt = clean_text
                content_hash = hashlib.sha256(raw_excerpt.encode("utf-8")).hexdigest()

            evidence_ref = EvidenceRef(
                evidence_id=f"ev_{uuid.uuid4().hex[:12]}",
                source_artifact=source_artifact,
                source_path=sanitized_path,
                source_location=source_location,
                evidence_type=evidence_type,
                evidence_excerpt=sanitized_excerpt,
                content_hash=content_hash,
                confidence=confidence,
                agent_name=agent_name,
                model_version=model_version,
                artifact_version=artifact_version,
            )
            return evidence_ref
        except Exception as exc:
            logger.exception(
                "create_evidence failed | source_path=%s type=%s | %s: %s",
                source_path,
                evidence_type,
                type(exc).__name__,
                exc,
            )
            raise

    def build_index(self, evidence_list: List[EvidenceRef]) -> Dict[str, EvidenceRef]:
        """Index a list of evidence items by their unique evidence_id."""
        try:
            return {item.evidence_id: item for item in evidence_list}
        except Exception as exc:
            logger.exception("build_index failed | %s: %s", type(exc).__name__, exc)
            raise


evidence_service = EvidenceService()
