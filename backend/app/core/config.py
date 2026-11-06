"""Application configuration settings for the Modernization Platform API."""

import json
import os
from pathlib import Path
from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = BACKEND_DIR.parent

try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(".env")
except ImportError:
    pass

def _default_phase6_target_profiles_json() -> str:
    def make_profile(version: str) -> dict:
        checks = [
            {"category": "build", "command": ["python", "-m", "compileall", "-q", "."]},
            {"category": "unit", "command": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]},
            {"category": "integration", "command": ["python", "-m", "pytest", "-k", "integration", "-q", "-p", "no:cacheprovider"]},
            {"category": "static", "command": ["python", "-m", "mypy", "--cache-dir=/tmp/mypy-cache", "--check-untyped-defs", "--explicit-package-bases", "."]},
            {"category": "security", "command": ["python", "-m", "bandit", "-r", "app", "-q"]},
            {"category": "dependency", "command": ["pip-audit", "--strict"]},
            {"category": "license", "command": ["pip-licenses", "--format=json"]},
            {"category": "runtime", "command": ["python", "-m", "pytest", "-k", "runtime", "-q", "-p", "no:cacheprovider"]},
            {"category": "api_compatibility", "command": ["python", "-m", "pytest", "-k", "api", "-q", "-p", "no:cacheprovider"]},
        ]
        system_checks = checks + [{"category": "schema", "command": ["python", "-m", "pytest", "-k", "schema", "-q", "-p", "no:cacheprovider"]}]
        runtime = os.getenv("SANDBOX_RUNTIME", "e2b-microvm" if os.getenv("E2B_API_KEY") else "docker-rootless")
        if runtime not in {"docker-rootless", "gvisor-rootless", "e2b-microvm"}:
            runtime = "docker-rootless"
        return {
            "version": version,
            "image": "sha256:afad74cbf6c87d0bd550e5b33496713aaeecafb45f052b9dc8bfc279435970f3",
            "runtime": runtime,
            "timeout": 180,
            "adapter": ["python", "/adapter.py"],
            "checks": checks,
            "system_checks": system_checks,
        }
    return json.dumps({
        "Python": make_profile("python-v1"),
        "python-fastapi": make_profile("python-fastapi-v1"),
        "Python / FastAPI": make_profile("python-fastapi-v1"),
        "FastAPI": make_profile("python-fastapi-v1"),
        "Django REST Framework": make_profile("django-drf-v1"),
        "TypeScript / NestJS": make_profile("typescript-nestjs-v1"),
        "Node / Express": make_profile("node-express-v1"),
        "Next.js": make_profile("typescript-nestjs-v1"),
        "Next.js (React)": make_profile("typescript-nestjs-v1"),
    })


try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        # Environment & Server
        ENVIRONMENT: str = Field(default="development", description="Runtime environment: development, staging, production, testing")
        DEBUG: bool = Field(default=True, description="Enable debug mode and detailed exception logs")
        PHASE5_LEGACY_IMAGE: str = Field(
            default="phase5-legacy-fixture@sha256:c4b08a30ed93afecac971193131d4dadcbea7d112915749b7864a38676d481fb",
            description="Immutable digest of Phase 5 legacy fixture Docker image",
        )
        PHASE5_LEGACY_COMMAND_JSON: str = Field(
            default='["python", "/adapter.py"]',
            description="Command argv for Phase 5 legacy adapter execution",
        )
        PHASE6_SANDBOX_IMAGE: str = ""
        PHASE6_CHECK_COMMANDS_JSON: str = "[]"
        PHASE6_TARGET_COMMAND_JSON: str = "[]"
        PHASE6_TARGET_PROFILES_JSON: str = Field(default_factory=_default_phase6_target_profiles_json)
        PHASE6_SANDBOX_PYTHON: str = "/usr/local/bin/python"
        PHASE6_SANDBOX_TIMEOUT: int = Field(default=180, ge=1, le=600)
        SANDBOX_CONTROLLER_URL: str = ""
        SANDBOX_DISPATCH_KEY: str = "a7281bc894ef201847192a0918efbc7102947194829104812739481928471928"
        SANDBOX_ATTESTATION_KEY: str = "e8392abf4812efd978432a10be28491c49e29a01cf6389174be89124a91823ef"
        PHASE6_MODEL_PROVIDER: str = ""
        PHASE6_MODEL_IDENTIFIER: str = ""
        PHASE6_MAX_OUTPUT_TOKENS: int = Field(default=16384, ge=128, le=32768)
        PHASE6_MAX_TASK_COST_USD: float = Field(default=1.0, gt=0, le=100)
        PHASE7_SANDBOX_IMAGE: str = ""
        PHASE7_CHECK_COMMANDS_JSON: str = "[]"
        PHASE7_SBOM_TOOL: str = ""
        PHASE7_PR_PROVIDER: str = ""
        PHASE7_GITHUB_REPOSITORY: str = ""
        PHASE7_GITHUB_TOKEN: str = ""
        PHASE7_GITHUB_API_URL: str = "https://api.github.com"
        PHASE7_PR_BASE_BRANCH: str = "main"
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
        ENABLE_LEGACY_CONTINUOUS_PIPELINE: bool = Field(
            default=False,
            description="Feature flag controlling deprecated legacy ContinuousPipelineService direct invocation"
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
        DEFAULT_JOB_BUDGET_INR: float = Field(default=15000.0, description="Default spend cap per job in INR (Rupees)")
        DEFAULT_JOB_BUDGET_USD: float = Field(default=15000.0, description="Default spend cap per job (INR platform currency)")
        MAX_REPAIR_ATTEMPTS: int = Field(default=3, description="Max inner-loop compile/test repair attempts")
        TOKEN_VELOCITY_LIMIT_PER_MINUTE: int = Field(default=100000, description="Token consumption rate limit")

        # Testing & Isolation Infrastructure (W02)
        TEST_ISOLATION_TOKEN: Optional[str] = Field(default=None, description="Cryptographic token issued only by disposable test fixtures")
        REAL_MODEL_SANDBOX_ENABLED: bool = Field(default=False, description="Explicit approval flag required for real LLM model acceptance lane")
        MAX_BUDGET_USD: float = Field(default=5.0, description="Strict budget ceiling for real model sandbox lane")

        # Sandboxing & Governance
        E2B_API_KEY: str = Field(default="", description="E2B Sandbox API Key for isolated MicroVM execution")
        SANDBOX_RUNTIME: str = Field(default="docker-unverified", description="Configured sandbox runtime claim; docker-unverified, gVisor-rootless, or e2b-microvm")
        SANDBOX_NETWORK_EGRESS: str = Field(default="air-gapped", description="Container egress: air-gapped or package-whitelist")
        ENFORCE_SECRET_REDACTION: bool = Field(default=True, description="Automatically mask credentials before storage")
        MIN_RATIONALE_LENGTH: int = Field(default=10, description="Minimum characters required for gate approval rationales")

        @field_validator("DATABASE_URL")
        @classmethod
        def validate_database_isolation(cls, v: str) -> str:
            env = os.getenv("ENVIRONMENT", "development").lower()
            if env == "testing":
                from app.core.testing_infrastructure import IsolationGuard
                IsolationGuard.verify_database_url(v, os.getenv("TEST_ISOLATION_TOKEN"))
            return v

        @field_validator("DEBUG", mode="before")
        @classmethod
        def parse_debug_bool(cls, v: Any) -> bool:
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                v_lower = v.strip().lower()
                if v_lower in ("true", "1", "t", "yes", "y", "debug", "dev", "development"):
                    return True
                if v_lower in ("false", "0", "f", "no", "n", "release", "prod", "production"):
                    return False
            return bool(v)

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

        @field_validator("SESSION_COOKIE_SECURE", mode="before")
        @classmethod
        def validate_cookie_secure(cls, v: Any) -> bool:
            env = os.getenv("ENVIRONMENT", "development").lower()
            if env == "production":
                return True
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                return v.strip().lower() in ("true", "1", "t", "yes", "y")
            return bool(v)

        @field_validator("ALLOWED_HOSTS")
        @classmethod
        def validate_allowed_hosts(cls, v: Any) -> List[str]:
            hosts = v if isinstance(v, list) else [str(v)]
            env = os.getenv("ENVIRONMENT", "development").lower()
            if env == "production":
                hosts = [h for h in hosts if h != "*"]
                if not hosts:
                    raise ValueError("ALLOWED_HOSTS cannot be empty or wildcard in production.")
            return hosts

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
        PHASE5_LEGACY_IMAGE: str = os.getenv("PHASE5_LEGACY_IMAGE", "phase5-legacy-fixture@sha256:c4b08a30ed93afecac971193131d4dadcbea7d112915749b7864a38676d481fb")
        PHASE5_LEGACY_COMMAND_JSON: str = os.getenv("PHASE5_LEGACY_COMMAND_JSON", '["python", "/adapter.py"]')
        PHASE6_SANDBOX_IMAGE: str = os.getenv("PHASE6_SANDBOX_IMAGE", "")
        PHASE6_CHECK_COMMANDS_JSON: str = os.getenv("PHASE6_CHECK_COMMANDS_JSON", "[]")
        PHASE6_TARGET_COMMAND_JSON: str = os.getenv("PHASE6_TARGET_COMMAND_JSON", "[]")
        _p6 = os.getenv("PHASE6_TARGET_PROFILES_JSON"); PHASE6_TARGET_PROFILES_JSON: str = _p6 if (_p6 and _p6.strip() not in ("", "{}")) else _default_phase6_target_profiles_json()
        PHASE6_SANDBOX_PYTHON: str = "/usr/local/bin/python"
        PHASE6_SANDBOX_TIMEOUT: int = 180
        SANDBOX_CONTROLLER_URL: str = os.getenv("SANDBOX_CONTROLLER_URL", "")
        SANDBOX_DISPATCH_KEY: str = os.getenv("SANDBOX_DISPATCH_KEY") or "a7281bc894ef201847192a0918efbc7102947194829104812739481928471928"
        SANDBOX_ATTESTATION_KEY: str = os.getenv("SANDBOX_ATTESTATION_KEY") or "e8392abf4812efd978432a10be28491c49e29a01cf6389174be89124a91823ef"
        PHASE6_MODEL_PROVIDER: str = os.getenv("PHASE6_MODEL_PROVIDER", "")
        PHASE6_MODEL_IDENTIFIER: str = os.getenv("PHASE6_MODEL_IDENTIFIER", "")
        PHASE6_MAX_OUTPUT_TOKENS: int = int(os.getenv("PHASE6_MAX_OUTPUT_TOKENS", "16384"))
        PHASE6_MAX_TASK_COST_USD: float = 1.0
        PHASE7_SANDBOX_IMAGE: str = os.getenv("PHASE7_SANDBOX_IMAGE", "")
        PHASE7_CHECK_COMMANDS_JSON: str = os.getenv("PHASE7_CHECK_COMMANDS_JSON", "[]")
        PHASE7_SBOM_TOOL: str = os.getenv("PHASE7_SBOM_TOOL", "")
        PHASE7_PR_PROVIDER: str = os.getenv("PHASE7_PR_PROVIDER", "")
        PHASE7_GITHUB_REPOSITORY: str = os.getenv("PHASE7_GITHUB_REPOSITORY", "")
        PHASE7_GITHUB_TOKEN: str = os.getenv("PHASE7_GITHUB_TOKEN", "")
        PHASE7_GITHUB_API_URL: str = os.getenv("PHASE7_GITHUB_API_URL", "https://api.github.com")
        PHASE7_PR_BASE_BRANCH: str = os.getenv("PHASE7_PR_BASE_BRANCH", "main")
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
        DEFAULT_JOB_BUDGET_INR: float = float(os.getenv("DEFAULT_JOB_BUDGET_INR", "15000.0"))
        DEFAULT_JOB_BUDGET_USD: float = float(os.getenv("DEFAULT_JOB_BUDGET_USD", "15000.0"))
        MAX_REPAIR_ATTEMPTS: int = int(os.getenv("MAX_REPAIR_ATTEMPTS", "3"))
        TOKEN_VELOCITY_LIMIT_PER_MINUTE: int = int(os.getenv("TOKEN_VELOCITY_LIMIT_PER_MINUTE", "100000"))
        TEST_ISOLATION_TOKEN: Optional[str] = os.getenv("TEST_ISOLATION_TOKEN", None)
        REAL_MODEL_SANDBOX_ENABLED: bool = os.getenv("REAL_MODEL_SANDBOX_ENABLED", "false").lower() in ("true", "1")
        MAX_BUDGET_USD: float = float(os.getenv("MAX_BUDGET_USD", "5.0"))
        E2B_API_KEY: str = os.getenv("E2B_API_KEY", "")
        SANDBOX_RUNTIME: str = os.getenv("SANDBOX_RUNTIME", "docker-unverified")
        SANDBOX_NETWORK_EGRESS: str = os.getenv("SANDBOX_NETWORK_EGRESS", "air-gapped")
        ENFORCE_SECRET_REDACTION: bool = True
        MIN_RATIONALE_LENGTH: int = 10


settings = Settings()
