"""Scoped CodeWriter. Generation is not execution evidence and cannot verify a module."""

import json
import logging
from pathlib import Path
from app.core.config import settings
from app.services.model_gateway import build_default_gateway

logger = logging.getLogger(__name__)
PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "phase6-codewriter-v1.txt"


class CodeWriterService:
    async def generate(self, context: dict, sources: dict, *, gateway=None):
        try:
            if gateway is None and (
                not settings.PHASE6_MODEL_PROVIDER
                or not settings.PHASE6_MODEL_IDENTIFIER
                or settings.PHASE6_MODEL_PROVIDER == "fake"
            ):
                raise ValueError(
                    "Phase 6 production model provider/model is not configured"
                )
            gateway = gateway or build_default_gateway()
            context = {
                k: v for k, v in context.items() if k not in ("approved_modules",)
            }
            context["cases"] = [
                c
                for c in context["cases"]
                if c.get("module") in (context["name"], context["module_id"])
            ] or context["cases"]
            if context.get("repair_feedback"):
                context["repair_feedback"] = {
                    k: v
                    for k, v in context["repair_feedback"].items()
                    if k not in ("repair_feedback",)
                }
            if (
                len(json.dumps({"task": context, "source_files": sources}).encode())
                > 262144
            ):
                raise ValueError(
                    "Module context exceeds the bounded model input; refine the approved module scope"
                )
            result = await gateway.complete(
                provider=settings.PHASE6_MODEL_PROVIDER,
                model=settings.PHASE6_MODEL_IDENTIFIER,
                max_retries=0,
                request={
                    "messages": [
                        {
                            "role": "system",
                            "content": PROMPT.read_text(encoding="utf-8"),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {"task": context, "source_files": sources},
                                sort_keys=True,
                            ),
                        },
                    ],
                    "max_tokens": settings.PHASE6_MAX_OUTPUT_TOKENS,
                    "temperature": 0,
                },
            )
            response = result.response
            output = response.output
            return (
                output,
                response.usage.model_dump(),
                {
                    "provider_attempts": result.attempts,
                    "prompt_version": "phase6-codewriter-v1",
                    "action": response.action,
                    "provider_request_id": response.provider_request_id,
                    "provider_metadata": response.provider_metadata,
                },
            )
        except Exception:
            logger.exception("CodeWriter.generate failed")
            raise

    async def execute_module_conversion(
        self,
        db,
        job,
        module,
        *,
        user=None,
        repair_instruction=None,
        correlation_id=None
    ):
        """Compatibility entry: dispatch through Supervisor; never synthesize successful work."""
        try:
            from app.services.supervisor_service import supervisor_service

            return await supervisor_service.run_module_conversion(
                db, job, module, user=user, repair_instruction=repair_instruction
            )
        except Exception:
            logger.exception("CodeWriter.execute_module_conversion failed")
            raise


code_writer_service = CodeWriterService()
