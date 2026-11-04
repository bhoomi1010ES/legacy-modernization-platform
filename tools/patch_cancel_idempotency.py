path = r"backend/app/services/supervisor_command_service.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

old_exec_terminal = '''            # 4. Check terminal states
            if current_status in JobStateMachine.TERMINAL_STATES:
                if command.command_type != SupervisorCommandType.RETRY_FAILED_JOB:
                    raise IllegalStateTransitionException(
                        current_state=current_status.value,
                        target_state="REJECTED",
                        reason=f"Job is in terminal state '{current_status.value}' and cannot accept commands.",
                    )'''

new_exec_terminal = '''            # 4. Check terminal states
            if current_status in JobStateMachine.TERMINAL_STATES:
                if command.command_type == SupervisorCommandType.CANCEL_JOB and current_status == JobStatus.CANCELLED:
                    return CommandReceipt(
                        command_id=command.command_id,
                        job_id=job.job_id,
                        command_type=command.command_type,
                        status="REPLAYED",
                        current_job_status=job.status,
                        generation=job.orchestration_generation,
                        checkpoint_sequence=job.last_checkpoint_sequence,
                        correlation_id=command.correlation_id,
                        causation_id=command.causation_id,
                    )
                if command.command_type != SupervisorCommandType.RETRY_FAILED_JOB:
                    raise IllegalStateTransitionException(
                        current_state=current_status.value,
                        target_state="REJECTED",
                        reason=f"Job is in terminal state '{current_status.value}' and cannot accept commands.",
                    )'''

assert old_exec_terminal in c, "old_exec_terminal not found"
c = c.replace(old_exec_terminal, new_exec_terminal, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Updated supervisor_command_service.py cancellation idempotency successfully")

