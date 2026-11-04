from pathlib import Path

test_file = Path("backend/tests/test_w03_schema_and_reconciliation.py")
content = test_file.read_text(encoding="utf-8")

old_audit = """        audit_stmt = (
            select(AuditEvent)
            .where(AuditEvent.event_type == "data.reconciliation_applied")
            .where(AuditEvent.target_resource == "database.reconciliation")
        )
        audit_res = await db_session.execute(audit_stmt)
        audit_event = audit_res.scalar_one_or_none()"""

new_audit = """        audit_stmt = (
            select(AuditEvent)
            .where(AuditEvent.event_type == "data.reconciliation_applied")
            .where(AuditEvent.target_resource == "database.reconciliation")
            .order_by(AuditEvent.created_at.desc())
        )
        audit_res = await db_session.execute(audit_stmt)
        audit_event = audit_res.scalars().first()"""

content = content.replace(old_audit, new_audit, 1)
test_file.write_text(content, encoding="utf-8")
print("Fixed audit_event query in test_w03_schema_and_reconciliation.py")

