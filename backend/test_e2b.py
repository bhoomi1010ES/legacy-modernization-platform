import os
from e2b import Sandbox

api_key = "e2b_2e4f304269fd97e1c7e4b6fd912ec05d5e8a825d"
os.environ["E2B_API_KEY"] = api_key

try:
    print("Creating E2B sandbox...")
    sb = Sandbox.create(timeout=60)
    print("Sandbox created:", sb.sandbox_id)
    res = sb.commands.run("python3 --version")
    print("Python version:", res.stdout)
    sb.kill()
    print("Sandbox killed successfully.")
except Exception as e:
    print("E2B Error:", type(e), e)

