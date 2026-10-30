from pathlib import Path

env_path = Path(".env")
text = env_path.read_text(encoding="utf-8")
if "PHASE6_MODEL_PROVIDER" not in text:
    phase6_block = """
# ------------------------------------------------------------------------------
# 8. Phase 6 Scoped Conversion & Independent Verification Sandbox
# ------------------------------------------------------------------------------
PHASE6_MODEL_PROVIDER=openai
PHASE6_MODEL_IDENTIFIER=gpt-4o-mini
PHASE6_SANDBOX_IMAGE=sha256:78c7f2fa233ebfc26669a41e52154c62ede5b0d16b821dd83ca2dc5aeab9fac5
PHASE6_TARGET_COMMAND_JSON=["python", "/adapter.py"]
PHASE6_CHECK_COMMANDS_JSON=[{"category":"build","command":["python","-m","compileall","-q","."]},{"category":"unit","command":["python","-m","pytest","/acceptance/test_calc.py","-q","-p","no:cacheprovider"]},{"category":"static","command":["python","-m","mypy","--cache-dir=/tmp/mypy-cache","--check-untyped-defs","--explicit-package-bases","."]},{"category":"security","command":["python","-m","bandit","-r",".","-q"]}]
"""
    if "\r\n" in text:
        phase6_block = phase6_block.replace("\n", "\r\n")
    env_path.write_text(text.rstrip() + "\r\n" + phase6_block.lstrip(), encoding="utf-8")
    print("SUCCESS")
else:
    print("ALREADY CONFIGURED")

