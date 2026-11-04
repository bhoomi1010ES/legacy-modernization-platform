from pathlib import Path

config_path = Path("backend/app/core/config.py")
content = config_path.read_text(encoding="utf-8")

# 1. Add fields to Settings class
field_insertion = '''        # Testing & Isolation Infrastructure (W02)
        TEST_ISOLATION_TOKEN: Optional[str] = Field(default=None, description="Cryptographic token issued only by disposable test fixtures")
        REAL_MODEL_SANDBOX_ENABLED: bool = Field(default=False, description="Explicit approval flag required for real LLM model acceptance lane")
        MAX_BUDGET_USD: float = Field(default=5.0, description="Strict budget ceiling for real model sandbox lane")

        # Sandboxing & Governance'''

content = content.replace("        # Sandboxing & Governance", field_insertion, 1)

# 2. Add validator
validator_insertion = '''        @field_validator("DATABASE_URL")
        @classmethod
        def validate_database_isolation(cls, v: str) -> str:
            env = os.getenv("ENVIRONMENT", "development").lower()
            if env == "testing":
                from app.core.testing_infrastructure import IsolationGuard
                IsolationGuard.verify_database_url(v, os.getenv("TEST_ISOLATION_TOKEN"))
            return v

        @field_validator("DEBUG", mode="before")'''

content = content.replace('        @field_validator("DEBUG", mode="before")', validator_insertion, 1)

# 3. Add to fallback Settings class
fallback_fields = '''        TEST_ISOLATION_TOKEN: Optional[str] = os.getenv("TEST_ISOLATION_TOKEN", None)
        REAL_MODEL_SANDBOX_ENABLED: bool = os.getenv("REAL_MODEL_SANDBOX_ENABLED", "false").lower() in ("true", "1")
        MAX_BUDGET_USD: float = float(os.getenv("MAX_BUDGET_USD", "5.0"))
        SANDBOX_RUNTIME: str = os.getenv("SANDBOX_RUNTIME", "gVisor-rootless")'''

content = content.replace('        SANDBOX_RUNTIME: str = os.getenv("SANDBOX_RUNTIME", "gVisor-rootless")', fallback_fields, 1)

config_path.write_text(content, encoding="utf-8")
print("Updated backend/app/core/config.py successfully.")

