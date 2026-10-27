"""Secret and sensitive environment data redaction service for prompts, traces, and logs."""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Union

logger = logging.getLogger(__name__)

# Standard secret pattern regexes
SECRET_PATTERNS = [
    # Generic API Keys / Tokens (Anthropic, OpenAI, GitHub, GitLab, etc.)
    (re.compile(r"sk-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}", re.IGNORECASE), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"gho_[a-zA-Z0-9]{36}", re.IGNORECASE), "[REDACTED_GITHUB_OAUTH]"),
    (re.compile(r"glpat-[a-zA-Z0-9\-]{20,}", re.IGNORECASE), "[REDACTED_GITLAB_TOKEN]"),
    (re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,48}", re.IGNORECASE), "[REDACTED_SLACK_TOKEN]"),
    # AWS Access Keys & Secrets
    (re.compile(r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}", re.IGNORECASE), "[REDACTED_AWS_KEY]"),
    # Private Keys (RSA, EC, DSA, OpenSSH)
    (
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
        "[REDACTED_PRIVATE_KEY]"
    ),
    # JWT / Bearer Tokens
    (re.compile(r"Bearer\s+ey[a-zA-Z0-9_\-]+\.ey[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+", re.IGNORECASE), "Bearer [REDACTED_JWT]"),
    # Database connection passwords: postgresql://user:password@host:port/db
    (re.compile(r"(postgres(?:ql)?(?:\+[a-z0-9]+)?://[^:]+:)([^@/]+)(@[^/]+)", re.IGNORECASE), r"\1[REDACTED_DB_PASSWORD]\3"),
    # Generic key=value or "key": "value" patterns for passwords/secrets
    (
        re.compile(r"""(?i)(["']?(?:password|secret|token|api_key|apikey|auth_token|client_secret)["']?\s*[:=]\s*["'])([^"'\s]{4,})(["'])"""),
        r"\1[REDACTED_SECRET]\3"
    ),
]


class SecretRedactor:
    """Provides high-performance, deterministic redaction of sensitive credentials and tokens."""

    def __init__(self, custom_sensitive_values: Optional[Set[str]] = None):
        self._custom_values: Set[str] = set()
        if custom_sensitive_values:
            for val in custom_sensitive_values:
                if val and len(val.strip()) >= 4:
                    self._custom_values.add(val.strip())

    def add_sensitive_value(self, value: str) -> None:
        """Dynamically registers an environment secret value for masking."""
        try:
            if value and len(value.strip()) >= 4:
                self._custom_values.add(value.strip())
        except Exception as exc:
            logger.exception("Failed to add sensitive value to SecretRedactor: %s", exc)

    def redact_text(self, text: str) -> str:
        """Scans and masks all secret tokens and registered values within a string."""
        try:
            if not text or not isinstance(text, str):
                return text

            result = text

            # 1. Redact known regex patterns
            for pattern, replacement in SECRET_PATTERNS:
                result = pattern.sub(replacement, result)

            # 2. Redact specific configured secrets (exact substring matching)
            for secret in self._custom_values:
                if secret in result:
                    result = result.replace(secret, "[REDACTED_ENV_SECRET]")

            return result
        except Exception as exc:
            logger.exception("SecretRedactor.redact_text failed: %s", exc)
            return "[REDACTED_ERROR]"

    def redact_object(self, obj: Any) -> Any:
        """Recursively sanitizes dicts, lists, strings, and primitives."""
        try:
            if isinstance(obj, str):
                return self.redact_text(obj)
            elif isinstance(obj, dict):
                redacted_dict = {}
                for k, v in obj.items():
                    # Mask value if key clearly indicates secret material
                    k_str = str(k).lower().replace("-", "_")
                    sensitive_names = {
                        "password", "passwd", "secret", "token", "access_token", "refresh_token",
                        "auth_token", "api_key", "apikey", "client_secret", "credential", "credentials",
                    }
                    is_sensitive = (
                        k_str in sensitive_names
                        or k_str.endswith(("_password", "_passwd", "_secret", "_api_key", "_credential"))
                        or (k_str.endswith("_token") and not k_str.endswith("_tokens"))
                    )
                    if is_sensitive:
                        redacted_dict[k] = "[REDACTED_SECRET_FIELD]"
                    else:
                        redacted_dict[k] = self.redact_object(v)
                return redacted_dict
            elif isinstance(obj, list):
                return [self.redact_object(item) for item in obj]
            elif isinstance(obj, tuple):
                return tuple(self.redact_object(item) for item in obj)
            elif isinstance(obj, set):
                return {self.redact_object(item) for item in obj}
            else:
                return obj
        except Exception as exc:
            logger.exception("SecretRedactor.redact_object failed: %s", exc)
            return obj


# Global default redactor instance initialized with active settings
_default_redactor: Optional[SecretRedactor] = None


def get_secret_redactor() -> SecretRedactor:
    """Returns singleton SecretRedactor initialized with system environment secrets."""
    global _default_redactor
    if _default_redactor is None:
        try:
            from app.core.config import settings
            secrets: Set[str] = set()
            if getattr(settings, "SECRET_KEY", None):
                secrets.add(settings.SECRET_KEY)
            if getattr(settings, "ANTHROPIC_API_KEY", None):
                secrets.add(settings.ANTHROPIC_API_KEY)
            if getattr(settings, "OPENAI_API_KEY", None):
                secrets.add(settings.OPENAI_API_KEY)
            _default_redactor = SecretRedactor(custom_sensitive_values=secrets)
        except Exception as exc:
            logger.exception("Failed to initialize singleton SecretRedactor: %s", exc)
            _default_redactor = SecretRedactor()
    return _default_redactor
