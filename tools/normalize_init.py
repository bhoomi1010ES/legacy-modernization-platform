with open("backend/app/models/__init__.py", "r", encoding="utf-8") as f:
    c = f.read()

c = c.replace('"WorkflowOutbox",\n', '"WorkflowOutbox",\n    "WorkerRegistry",\n')
c = c.replace('"WorkflowOutbox",\r\n', '"WorkflowOutbox",\r\n    "WorkerRegistry",\r\n')

with open("backend/app/models/__init__.py", "w", encoding="utf-8") as f:
    f.write(c)

print("Updated models/__init__.py with WorkerRegistry")

