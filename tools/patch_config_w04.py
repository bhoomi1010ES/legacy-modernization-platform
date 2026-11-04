path = r"backend/app/core/config.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

target = '        ALLOWED_HOSTS: Any = Field(\n            default=["localhost", "127.0.0.1", "testserver"],\n            description="Allowed HTTP host header domains"\n        )'
rep = '''        ALLOWED_HOSTS: Any = Field(
            default=["localhost", "127.0.0.1", "testserver"],
            description="Allowed HTTP host header domains"
        )
        ENABLE_LEGACY_CONTINUOUS_PIPELINE: bool = Field(
            default=False,
            description="Feature flag controlling deprecated legacy ContinuousPipelineService direct invocation"
        )'''

if target not in c:
    target = target.replace("\n", "\r\n")
    rep = rep.replace("\n", "\r\n")

assert target in c, "Target not found in config.py"
c = c.replace(target, rep, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)
print("Updated config.py successfully")

