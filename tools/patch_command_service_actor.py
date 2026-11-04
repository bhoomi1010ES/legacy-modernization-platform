path = r"backend/app/services/supervisor_command_service.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

helper = '''def normalize_actor_type(actor_type: str) -> str:
    if actor_type in ("USER", "HUMAN"):
        return "USER"
    if actor_type in ("SYSTEM", "SERVICE"):
        return "SYSTEM"
    if actor_type in ("AGENT", "MODEL"):
        return "AGENT"
    return "USER"
'''

c = c.replace("def utc_now() -> datetime:\n    return datetime.now(timezone.utc)\n", "def utc_now() -> datetime:\n    return datetime.now(timezone.utc)\n\n" + helper)

c = c.replace("actor_type=command.actor_type,", "actor_type=normalize_actor_type(command.actor_type),")

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Updated supervisor_command_service.py actor_type handling successfully")

