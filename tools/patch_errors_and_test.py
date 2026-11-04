from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 1. Update errors.py
errors_path = ROOT / "backend" / "app" / "core" / "errors.py"
errors_text = errors_path.read_text(encoding="utf-8")

old_forbidden = """class ForbiddenException(PlatformException):
    def __init__(self, message: str = "You do not have permission to perform this action."):
        super().__init__(code="FORBIDDEN", message=message, status_code=403)"""

new_forbidden = """class ForbiddenException(PlatformException):
    def __init__(
        self,
        message: str = "You do not have permission to perform this action.",
        details: Optional[list] = None,
    ):
        super().__init__(code="FORBIDDEN", message=message, status_code=403, details=details)"""

if "details: Optional[list] = None" not in errors_text:
    if old_forbidden in errors_text:
        errors_text = errors_text.replace(old_forbidden, new_forbidden)
    else:
        old_crlf = old_forbidden.replace("\n", "\r\n")
        new_crlf = new_forbidden.replace("\n", "\r\n")
        errors_text = errors_text.replace(old_crlf, new_crlf)
    errors_path.write_text(errors_text, encoding="utf-8")
    print("Updated ForbiddenException to accept details")

# 2. Update test_w01_security.py
test_path = ROOT / "backend" / "tests" / "test_w01_security.py"
test_text = test_path.read_text(encoding="utf-8")

target_step2 = """    # 2. Attempt role promotion without admin auth -> 401 Unauthorized
    unauth_resp = client.post(
        f"/api/v1/auth/users/{target_user_id}/role",
        json={"role": "REVIEWER", "reason": "Promote to code reviewer"},
    )"""

fixed_step2 = """    # 2. Attempt role promotion without admin auth -> 401 Unauthorized
    client.cookies.clear()
    unauth_resp = client.post(
        f"/api/v1/auth/users/{target_user_id}/role",
        json={"role": "REVIEWER", "reason": "Promote to code reviewer"},
    )"""

if "client.cookies.clear()\n    unauth_resp" not in test_text and "client.cookies.clear()\r\n    unauth_resp" not in test_text:
    if target_step2 in test_text:
        test_text = test_text.replace(target_step2, fixed_step2)
    else:
        old_crlf = target_step2.replace("\n", "\r\n")
        new_crlf = fixed_step2.replace("\n", "\r\n")
        test_text = test_text.replace(old_crlf, new_crlf)
    test_path.write_text(test_text, encoding="utf-8")
    print("Updated test_w01_security.py step 2 clear cookies")

