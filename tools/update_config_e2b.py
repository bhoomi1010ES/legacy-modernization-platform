import re

CONFIG_PATH = "backend/app/core/config.py"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    content = f.read()

target1 = """        # Sandboxing & Governance
        SANDBOX_RUNTIME: str = Field(default="docker-unverified", description="Configured sandbox runtime claim; docker-unverified makes no rootless or gVisor isolation claim")"""

rep1 = """        # Sandboxing & Governance
        E2B_API_KEY: str = Field(default="", description="E2B Sandbox API Key for isolated MicroVM execution")
        SANDBOX_RUNTIME: str = Field(default="docker-unverified", description="Configured sandbox runtime claim; docker-unverified, gVisor-rootless, or e2b-microvm")"""

target2 = """        SANDBOX_RUNTIME: str = os.getenv("SANDBOX_RUNTIME", "docker-unverified")"""
rep2 = """        E2B_API_KEY: str = os.getenv("E2B_API_KEY", "")
        SANDBOX_RUNTIME: str = os.getenv("SANDBOX_RUNTIME", "docker-unverified")"""

assert target1 in content, "Target 1 not found"
assert target2 in content, "Target 2 not found"

content = content.replace(target1, rep1, 1)
content = content.replace(target2, rep2, 1)

with open(CONFIG_PATH, "w", encoding="utf-8") as f:
    f.write(content)

print("Successfully updated backend/app/core/config.py with E2B_API_KEY")

