"""Application configuration settings for the Modernization Platform API."""

import json
import os
from pathlib import Path
from typing import Any, List
from pydantic import BaseModel, Field, field_validator

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = BACKEND_DIR.parent

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        # Environment & Server
        ENVIRONMENT: str = Field(default="development", description="Runtime environment: development, staging, production, testing")
        DEBUG: bool = Field(default=True, description="Enable debug mode and detailed exception logs")
        PROJECT_NAME: str = Field(default="Multi-Agent Legacy Code Modernization Platform API", description="Service name")
        VERSION: str = Field(default="1.0.0", description="API Version")
        API_V1_PREFIX: str = Field(default="/api/v1", description="Prefix for v1 REST endpoints")
        HOST: str = Field(default="127.0.0.1", description="Bind host address")
        PORT: int = Field(default=8000, description="Bind port")

        # Security & Authentication
        SECRET_KEY: str = Field(
            default="phase-0-development-secret-key-change-in-production-min32bytes!",
            description="Cryptographic secret key for signing sessions and JWT tokens"
        )
        SESSION_COOKIE_NAME: str = Field(default="rebase_session_id", description="Name of the HTTP session cookie")
        SESSION_MAX_AGE_SECONDS: int = Field(default=86400, description="Session lifetime in seconds (24 hours)")
        SESSION_COOKIE_SECURE: bool = Field(default=False, description="Set True in production with HTTPS")
        SESSION_COOKIE_HTTPONLY: bool = Field(default=True, description="Prevent JavaScript access to session cookie")
        SESSION_COOKIE_SAMESITE: str = Field(default="lax", description="SameSite cookie policy: lax, strict, none")

        # CORS & Host Boundaries
        CORS_ALLOWED_ORIGINS: Any = Field(
            default=[
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:8080",
                "http://localhost:5173",
                "http://127.0.0.1:8080",
                "http://127.0.0.1:5173",
            ],
            description="Allowed CORS origin domains"
        )
        ALLOWED_HOSTS: Any = Field(
            default=["localhost", "127.0.0.1", "testserver"],
            description="Allowed HTTP host header domains"
        )

        # Database & Cache (PostgreSQL & Redis for Phase 1 persistence)
        DATABASE_URL: str = Field(
            default="postgresql+asyncpg://rebase_user:rebase_dev_password@localhost:5432/rebase_db",
            description="Async PostgreSQL connection URI"
        )
        REDIS_URL: str = Field(
            default="redis://localhost:6379/0",
            description="Redis connection URI for state checkpoints and rate limits"
        )
        ARTIFACT_STORAGE_PATH: str = Field(
            default="./artifacts",
            description="Local or S3 URI for versioned deliverable artifacts"
        )

        # Autonomous Agents & LLM Model Providers
        ANTHROPIC_API_KEY: str = Field(default="", description="Anthropic API key for Claude 3.5 Sonnet specialist agents")
        OPENAI_API_KEY: str = Field(default="", description="OpenAI API key (optional fallback)")
        DEFAULT_JOB_BUDGET_USD: float = Field(default=150.0, description="Default spend cap per job in USD")
        MAX_REPAIR_ATTEMPTS: int = Field(default=3, description="Max inner-loop compile/test repair attempts")
        TOKEN_VELOCITY_LIMIT_PER_MINUTE: int = Field(default=100000, description="Token consumption rate limit")

        # Sandboxing & Governance
        SANDBOX_RUNTIME: str = Field(default="gVisor-rootless", description="Sandbox runtime: gVisor-rootless or docker-rootless")
        SANDBOX_NETWORK_EGRESS: str = Field(default="air-gapped", description="Container egress: air-gapped or package-whitelist")
        ENFORCE_SECRET_REDACTION: bool = Field(default=True, description="Automatically mask credentials before storage")
        MIN_RATIONALE_LENGTH: int = Field(default=10, description="Minimum characters required for gate approval rationales")

        @field_validator("CORS_ALLOWED_ORIGINS", "ALLOWED_HOSTS")
        @classmethod
        def parse_comma_separated_list(cls, v: Any) -> List[str]:
            if isinstance(v, str):
                v_clean = v.strip()
                if v_clean.startswith("[") and v_clean.endswith("]"):
                    try:
                        return json.loads(v_clean)
                    except Exception:
                        pass
                return [item.strip() for item in v_clean.split(",") if item.strip()]
            if isinstance(v, (list, set, tuple)):
                return list(v)
            return [str(v)]

        @field_validator("SECRET_KEY")
        @classmethod
        def validate_secret_key(cls, v: str) -> str:
            env = os.getenv("ENVIRONMENT", "development").lower()
            if env == "production":
                if len(v) < 32 or "development" in v.lower() or "phase-0" in v.lower() or "change" in v.lower():
                    raise ValueError(
                        "Insecure SECRET_KEY detected for production environment. Must be at least 32 cryptographically secure characters."
                    )
            return v

        model_config = SettingsConfigDict(
            env_file=(
                str(BACKEND_DIR / ".env"),
                str(ROOT_DIR / ".env"),
                ".env",
            ),
            env_file_encoding="utf-8",
            case_sensitive=True,
            extra="ignore",
        )

except ImportError:
    class Settings(BaseModel):  # type: ignore[no-redef]
        ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
        DEBUG: bool = os.getenv("DEBUG", "true").lower() in ("true", "1", "t")
        PROJECT_NAME: str = os.getenv("PROJECT_NAME", "Multi-Agent Legacy Code Modernization Platform API")
        VERSION: str = os.getenv("VERSION", "1.0.0")
        API_V1_PREFIX: str = os.getenv("API_V1_PREFIX", "/api/v1")
        HOST: str = os.getenv("HOST", "127.0.0.1")
        PORT: int = int(os.getenv("PORT", "8000"))
        SECRET_KEY: str = os.getenv("SECRET_KEY", "phase-0-development-secret-key-change-in-production-min32bytes!")
        SESSION_COOKIE_NAME: str = os.getenv("SESSION_COOKIE_NAME", "rebase_session_id")
        SESSION_MAX_AGE_SECONDS: int = int(os.getenv("SESSION_MAX_AGE_SECONDS", "86400"))
        SESSION_COOKIE_SECURE: bool = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in ("true", "1")
        SESSION_COOKIE_HTTPONLY: bool = True
        SESSION_COOKIE_SAMESITE: str = os.getenv("SESSION_COOKIE_SAMESITE", "lax")
        CORS_ALLOWED_ORIGINS: List[str] = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8080",
            "http://localhost:5173",
            "http://127.0.0.1:8080",
            "http://127.0.0.1:5173",
        ]
        ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1", "testserver"]
        DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://rebase_user:rebase_dev_password@localhost:5432/rebase_db")
        REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        ARTIFACT_STORAGE_PATH: str = os.getenv("ARTIFACT_STORAGE_PATH", "./artifacts")
        ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
        OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
        DEFAULT_JOB_BUDGET_USD: float = float(os.getenv("DEFAULT_JOB_BUDGET_USD", "150.0"))
        MAX_REPAIR_ATTEMPTS: int = int(os.getenv("MAX_REPAIR_ATTEMPTS", "3"))
        TOKEN_VELOCITY_LIMIT_PER_MINUTE: int = int(os.getenv("TOKEN_VELOCITY_LIMIT_PER_MINUTE", "100000"))
        SANDBOX_RUNTIME: str = os.getenv("SANDBOX_RUNTIME", "gVisor-rootless")
        SANDBOX_NETWORK_EGRESS: str = os.getenv("SANDBOX_NETWORK_EGRESS", "air-gapped")
        ENFORCE_SECRET_REDACTION: bool = True
        MIN_RATIONALE_LENGTH: int = 10


settings = Settings()
