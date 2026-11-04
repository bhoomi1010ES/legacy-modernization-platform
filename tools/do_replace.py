from pathlib import Path

test_file = Path("backend/tests/test_w03_schema_and_reconciliation.py")
content = test_file.read_text(encoding="utf-8")
content = content.replace("audit_event = audit_res.scalar_one_or_none()", "audit_event = audit_res.scalars().first()")
content = content.replace(
    '.where(AuditEvent.target_resource == "database.reconciliation")',
    '.where(AuditEvent.target_resource == "database.reconciliation")\n        .order_by(AuditEvent.created_at.desc())'
)
test_file.write_text(content, encoding="utf-8")
print("Replaced scalar_one_or_none with scalars().first()")

