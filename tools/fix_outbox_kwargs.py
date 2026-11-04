path = r"backend/app/services/supervisor_command_service.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

target = '''        # Enqueue in WorkflowOutbox
        outbox_event = WorkflowOutbox(
            aggregate_type="job",
            aggregate_id=command.job_id,
            event_type=f"COMMAND_{command.command_type.value}",
            payload={
                "command_id": str(command.command_id),
                "command_type": command.command_type.value,
                "actor_id": command.actor_id,
                "actor_type": command.actor_type,
                "payload": command.payload,
            },
            idempotency_key=command.idempotency_key or str(command.command_id),
        )'''

rep = '''        # Enqueue in WorkflowOutbox
        outbox_event = WorkflowOutbox(
            job_id=command.job_id,
            event_type=f"COMMAND_{command.command_type.value}",
            payload={
                "command_id": str(command.command_id),
                "command_type": command.command_type.value,
                "actor_id": command.actor_id,
                "actor_type": command.actor_type,
                "payload": command.payload,
            },
            idempotency_key=command.idempotency_key or str(command.command_id),
        )'''

assert target in c, "target not found in supervisor_command_service.py"
c = c.replace(target, rep, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Updated supervisor_command_service.py WorkflowOutbox successfully")

