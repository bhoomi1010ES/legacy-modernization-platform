import os
from e2b import Sandbox

api_key = "e2b_2e4f304269fd97e1c7e4b6fd912ec05d5e8a825d"
os.environ["E2B_API_KEY"] = api_key

sb = Sandbox.create(timeout=60)
try:
    res = sb.commands.run("sudo mkdir -p /work && sudo chown -R $(id -u):$(id -g) /work && ls -ld /work")
    print("SUDO WORK DIR RESULT:", res.stdout)
finally:
    sb.kill()

