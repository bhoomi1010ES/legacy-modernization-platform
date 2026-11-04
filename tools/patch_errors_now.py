from pathlib import Path

errors_path = Path("backend/app/core/errors.py")
text = errors_path.read_text(encoding="utf-8")

old_str = 'class ForbiddenException(PlatformException):\n    def __init__(self, message: str = "You do not have permission to perform this action."):\n        super().__init__(code="FORBIDDEN", message=message, status_code=403)'
old_str_crlf = 'class ForbiddenException(PlatformException):\r\n    def __init__(self, message: str = "You do not have permission to perform this action."):\r\n        super().__init__(code="FORBIDDEN", message=message, status_code=403)'

new_str = 'class ForbiddenException(PlatformException):\n    def __init__(\n        self,\n        message: str = "You do not have permission to perform this action.",\n        details: Optional[list] = None,\n    ):\n        super().__init__(code="FORBIDDEN", message=message, status_code=403, details=details)'

if old_str in text:
    text = text.replace(old_str, new_str)
elif old_str_crlf in text:
    text = text.replace(old_str_crlf, new_str)
else:
    print("Could not find old_str")

errors_path.write_text(text, encoding="utf-8")
print("Done patching errors.py")

