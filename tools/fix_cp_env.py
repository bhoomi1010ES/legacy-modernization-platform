path = r"backend/app/services/continuous_pipeline.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

target = 'if getattr(settings, "APP_ENV", "development") == "production" and not getattr(settings, "ENABLE_LEGACY_CONTINUOUS_PIPELINE", False):'
rep = 'if (getattr(settings, "ENVIRONMENT", "development") == "production" or getattr(settings, "APP_ENV", "") == "production") and not getattr(settings, "ENABLE_LEGACY_CONTINUOUS_PIPELINE", False):'

assert target in c, "target not found in continuous_pipeline.py"
c = c.replace(target, rep, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Updated continuous_pipeline.py check successfully")

