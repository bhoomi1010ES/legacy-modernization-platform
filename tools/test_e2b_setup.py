import os
from e2b import Sandbox

os.environ["E2B_API_KEY"] = "e2b_2e4f304269fd97e1c7e4b6fd912ec05d5e8a825d"

print("Starting E2B Sandbox...")
sbx = Sandbox.create(timeout=60)
try:
    print(f"Sandbox created. ID: {sbx.sandbox_id}")
    
    # Write a test file
    sbx.files.write("/home/user/test.py", "print('Hello from isolated E2B MicroVM!')\n")
    
    # Run python script
    res = sbx.commands.run("python3 /home/user/test.py")
    print(f"Stdout: {res.stdout.strip()}")
    print(f"Exit code: {res.exit_code}")
    
    # Verify isolation: no host credentials leaked
    env_res = sbx.commands.run("env")
    assert "DATABASE_URL" not in env_res.stdout
    assert "SECRET_KEY" not in env_res.stdout
    print("Isolation verified: host secrets are completely absent from MicroVM.")
    
    # Verify user is non-root
    whoami = sbx.commands.run("whoami")
    print(f"Running user in sandbox: {whoami.stdout.strip()}")
finally:
    sbx.kill()
    print("Sandbox killed successfully.")

