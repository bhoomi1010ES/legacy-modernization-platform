path = r"backend/app/services/continuous_pipeline.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

target = '''    def trigger_continuous_pipeline(
        self,
        job_id: uuid.UUID,
        actor_id: Optional[uuid.UUID] = None,
        correlation_id: Optional[str] = None,
    ) -> asyncio.Task:
        """Kicks off continuous execution in background without blocking the caller."""
        return supervisor_service.schedule_drive(
            job_id, correlation_id=correlation_id or f"drive-{uuid.uuid4().hex[:12]}"
        )'''

rep = '''    def trigger_continuous_pipeline(
        self,
        job_id: uuid.UUID,
        actor_id: Optional[uuid.UUID] = None,
        correlation_id: Optional[str] = None,
    ) -> asyncio.Task:
        """Kicks off continuous execution in background without blocking the caller."""
        from app.core.config import settings
        from app.core.errors import ConflictException
        if getattr(settings, "APP_ENV", "development") == "production" and not getattr(settings, "ENABLE_LEGACY_CONTINUOUS_PIPELINE", False):
            raise ConflictException(
                "Direct invocation of deprecated ContinuousPipelineService is disabled in production. Use SupervisorCommandService."
            )
        logger.warning(
            "ContinuousPipelineService.trigger_continuous_pipeline is deprecated; delegating to supervisor_service.schedule_drive | job_id=%s", job_id
        )
        return supervisor_service.schedule_drive(
            job_id, correlation_id=correlation_id or f"drive-{uuid.uuid4().hex[:12]}"
        )'''

if target not in c:
    target = target.replace("\n", "\r\n")
    rep = rep.replace("\n", "\r\n")

assert target in c, "Target not found in continuous_pipeline.py"
c = c.replace(target, rep, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)
print("Updated continuous_pipeline.py successfully")

