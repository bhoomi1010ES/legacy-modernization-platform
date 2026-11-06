import os
from e2b import Sandbox

api_key = "e2b_2e4f304269fd97e1c7e4b6fd912ec05d5e8a825d"
os.environ["E2B_API_KEY"] = api_key

sb = Sandbox.create(timeout=60)
res = sb.commands.run("python3 -m pip list")
print("Installed in E2B:\n", res.stdout[:500])
sb.kill()

