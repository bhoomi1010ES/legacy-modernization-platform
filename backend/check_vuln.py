import os
from e2b import Sandbox
from e2b.sandbox.commands.command_handle import CommandExitException

os.environ["E2B_API_KEY"] = "e2b_2e4f304269fd97e1c7e4b6fd912ec05d5e8a825d"
sb = Sandbox.create(timeout=60)
try:
    sb.commands.run("python3 -m pip install -q -U pip setuptools certifi pip-audit")
    r = sb.commands.run("python3 -m pip_audit --desc")
    print("STDOUT:\n", r.stdout)
except CommandExitException as e:
    print("STDOUT:\n", e.stdout)
    print("STDERR:\n", e.stderr)
finally:
    sb.kill()
