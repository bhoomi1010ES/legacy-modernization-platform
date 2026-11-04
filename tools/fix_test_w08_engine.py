from pathlib import Path

p = Path("backend/tests/test_w08_planner_dag_and_scheduler.py")
text = p.read_text(encoding="utf-8")

# Replace custom engine creation with app.core.database import
old_engine_code = """async_engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)"""

new_engine_code = """from app.core.database import AsyncSessionLocal"""

assert old_engine_code in text, "old_engine_code not found"
text = text.replace(old_engine_code, new_engine_code, 1)

p.write_text(text, encoding="utf-8")
print("Successfully replaced custom engine with app.core.database.AsyncSessionLocal")

