path = r"backend/app/api/v1/jobs.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# Add import
import_stmt = "from app.services.supervisor_command_service import supervisor_command_service, BaseSupervisorCommand, CommandReceipt, CancelJobCommand, PauseJobCommand, ResumeJobCommand\n"
if "supervisor_command_service" not in c:
    c = import_stmt + c

# Update pause_job to use supervisor_command_service
old_pause = '''    paused = await supervisor_service.pause(
        db, job.job_id, actor_id=str(user.user_id), reason="Paused by authorized user.",
        correlation_id=getattr(request.state, "correlation_id", None),
    )'''

new_pause = '''    corr_id = getattr(request.state, "correlation_id", None)
    await supervisor_command_service.execute_command(
        db,
        PauseJobCommand(
            job_id=job.job_id,
            actor_id=str(user.user_id),
            actor_role=getattr(user, "role_id", getattr(user, "role", "DEVELOPER")),
            reason="Paused by authorized user.",
            correlation_id=corr_id,
        )
    )
    paused = await db.get(Job, job.job_id)'''

if old_pause in c:
    c = c.replace(old_pause, new_pause, 1)
elif old_pause.replace("\n", "\r\n") in c:
    c = c.replace(old_pause.replace("\n", "\r\n"), new_pause.replace("\n", "\r\n"), 1)

# Update resume_job to use supervisor_command_service
old_resume = '''    resumed = await supervisor_service.resume(
        db, job.job_id, actor_id=str(user.user_id),
        correlation_id=getattr(request.state, "correlation_id", None),
    )'''

new_resume = '''    corr_id = getattr(request.state, "correlation_id", None)
    await supervisor_command_service.execute_command(
        db,
        ResumeJobCommand(
            job_id=job.job_id,
            actor_id=str(user.user_id),
            actor_role=getattr(user, "role_id", getattr(user, "role", "DEVELOPER")),
            correlation_id=corr_id,
        )
    )
    resumed = await db.get(Job, job.job_id)'''

if old_resume in c:
    c = c.replace(old_resume, new_resume, 1)
elif old_resume.replace("\n", "\r\n") in c:
    c = c.replace(old_resume.replace("\n", "\r\n"), new_resume.replace("\n", "\r\n"), 1)

# Update cancel_job to use supervisor_command_service
old_cancel = '''    correlation_id = getattr(request.state, "correlation_id", None)
    cancelled_job = await supervisor_service.cancel(
        db, job.job_id,
        actor_id=str(user.user_id),
        correlation_id=correlation_id,
    )'''

new_cancel = '''    correlation_id = getattr(request.state, "correlation_id", None)
    await supervisor_command_service.execute_command(
        db,
        CancelJobCommand(
            job_id=job.job_id,
            actor_id=str(user.user_id),
            actor_role=getattr(user, "role_id", getattr(user, "role", "DEVELOPER")),
            reason="Cancelled by authorized user.",
            correlation_id=correlation_id,
        )
    )
    cancelled_job = await db.get(Job, job.job_id)'''

if old_cancel in c:
    c = c.replace(old_cancel, new_cancel, 1)
elif old_cancel.replace("\n", "\r\n") in c:
    c = c.replace(old_cancel.replace("\n", "\r\n"), new_cancel.replace("\n", "\r\n"), 1)

# Add enqueue_workflow_command endpoint
new_endpoint = '''
@router.post(
    "/{job_id}/commands",
    response_model=CommandReceipt,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue a workflow command for authoritative supervisor processing",
    operation_id="jobs_enqueue_command",
)
async def enqueue_workflow_command(
    job_id: str,
    command_in: BaseSupervisorCommand,
    request: Request,
    access: Tuple[Job, User] = Depends(require_job_access(permission="job:read")),
    db: AsyncSession = Depends(get_db),
) -> CommandReceipt:
    job, user = access
    command_in.job_id = job.job_id
    command_in.actor_id = str(user.user_id)
    command_in.actor_type = "HUMAN"
    command_in.actor_role = getattr(user, "role_id", getattr(user, "role", "DEVELOPER"))
    command_in.correlation_id = getattr(request.state, "correlation_id", None)
    return await supervisor_command_service.enqueue_command(db, command_in)
'''

target_anchor = "@router.post(\n    \"/{job_id}/intake\","
if target_anchor in c:
    c = c.replace(target_anchor, new_endpoint + "\n" + target_anchor, 1)
elif target_anchor.replace("\n", "\r\n") in c:
    c = c.replace(target_anchor.replace("\n", "\r\n"), new_endpoint.replace("\n", "\r\n") + "\r\n" + target_anchor.replace("\n", "\r\n"), 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Updated jobs.py successfully")

