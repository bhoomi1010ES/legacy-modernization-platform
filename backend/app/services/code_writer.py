"""Scoped CodeWriter. Generation is not execution evidence and cannot verify a module."""

import json
import logging
from pathlib import Path
from app.core.config import settings
from app.core.errors import IncompleteModelOutputError, MalformedModelOutputError
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
                rf = context["repair_feedback"]
                context["repair_feedback"] = {
                    "failed_checks": [
                        c for c in rf.get("checks", []) if c.get("status") != "PASS"
                    ],
                    "failed_cases": [
                        {k: c[k] for k in ("test_case_id", "status", "command") if k in c}
                        for c in rf.get("results", [])
                        if c.get("status") != "PASS"
                    ][:20],
                    "findings": rf.get("review", {}).get("findings", []),
                    "failure_signature": rf.get("failure_signature"),
                }
            if (
                len(json.dumps({"task": context, "source_files": sources}).encode())
                > 2097152
            ):
                raise ValueError(
                    "Module context exceeds the bounded model input; refine the approved module scope"
                )
            req = {
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
            }
            if settings.PHASE6_MODEL_PROVIDER == "openai":
                req["response_format"] = {"type": "json_object"}
            result = await gateway.complete(
                provider=settings.PHASE6_MODEL_PROVIDER,
                model=settings.PHASE6_MODEL_IDENTIFIER,
                max_retries=2,
                request=req,
            )
            response = result.response
            output = response.output

            # If monolithic generation hit the token limit and we have multiple files, attempt chunked generation
            finish_reason = response.provider_metadata.get("finish_reason")
            if finish_reason == "length" and len(sources) > 1:
                logger.warning(
                    "CodeWriter monolithic generation hit token ceiling (finish_reason='length'); attempting chunked generation for %d files",
                    len(sources),
                )
                try:
                    return await self._generate_chunks(context, sources, gateway)
                except Exception as chunk_exc:
                    logger.warning("Chunked generation fallback failed: %s; preserving monolithic usage", chunk_exc)

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

    async def _generate_chunks(self, context: dict, sources: dict, gateway):
        """Bounded multi-chunk generation when module files exceed single-prompt token ceiling."""
        items = list(sources.items())
        chunk_size = 3
        chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
        all_files: dict[str, str] = {}
        all_notes: list[str] = []
        all_assumptions: list[str] = []
        all_test_commands: list[list[str]] = []
        total_in_tokens = 0
        total_out_tokens = 0
        total_cost = 0.0
        total_attempts = 0
        last_response = None

        for chunk_idx, chunk in enumerate(chunks):
            chunk_dict = dict(chunk)
            chunk_context = {
                **context,
                "chunk_info": f"Chunk {chunk_idx + 1} of {len(chunks)} ({list(chunk_dict.keys())})",
                "target_subset_files": list(chunk_dict.keys()),
            }
            req = {
                "messages": [
                    {
                        "role": "system",
                        "content": PROMPT.read_text(encoding="utf-8") + "\n\nConvert ONLY the source files provided in this chunk into valid ChangeSet JSON.",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"task": chunk_context, "source_files": chunk_dict},
                            sort_keys=True,
                        ),
                    },
                ],
                "max_tokens": settings.PHASE6_MAX_OUTPUT_TOKENS,
                "temperature": 0,
            }
            if settings.PHASE6_MODEL_PROVIDER == "openai":
                req["response_format"] = {"type": "json_object"}

            result = await gateway.complete(
                provider=settings.PHASE6_MODEL_PROVIDER,
                model=settings.PHASE6_MODEL_IDENTIFIER,
                max_retries=2,
                request=req,
            )
            resp = result.response
            total_attempts += result.attempts
            usage_d = resp.usage.model_dump()
            total_in_tokens += usage_d.get("input_tokens", 0)
            total_out_tokens += usage_d.get("output_tokens", 0)
            total_cost += float(usage_d.get("cost_usd", 0.0))
            last_response = resp

            if resp.provider_metadata.get("finish_reason") == "length":
                raise IncompleteModelOutputError(
                    f"Model generation truncated during chunk {chunk_idx + 1}: finish_reason='length'."
                )

            content = resp.output.get("content", "") if isinstance(resp.output, dict) else str(resp.output)
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            try:
                chunk_json = json.loads(content)
            except json.JSONDecodeError as jde:
                raise MalformedModelOutputError(
                    f"Invalid JSON in chunk {chunk_idx + 1}: {jde}"
                ) from jde

            chunk_files = chunk_json.get("files", {})
            if not isinstance(chunk_files, dict):
                raise MalformedModelOutputError(f"Chunk {chunk_idx + 1} did not return a 'files' object")
            all_files.update(chunk_files)
            if chunk_json.get("design_notes"):
                all_notes.append(str(chunk_json["design_notes"]))
            if isinstance(chunk_json.get("assumptions"), list):
                all_assumptions.extend(chunk_json["assumptions"])
            if isinstance(chunk_json.get("test_commands"), list):
                all_test_commands.extend(chunk_json["test_commands"])

        combined_output = {
            "content": json.dumps({
                "files": all_files,
                "design_notes": "\n\n".join(all_notes) or "Modular chunked conversion",
                "assumptions": list(dict.fromkeys(all_assumptions)),
                "test_commands": all_test_commands,
            })
        }
        combined_usage = {
            "input_tokens": total_in_tokens,
            "output_tokens": total_out_tokens,
            "cost_usd": round(total_cost, 4),
        }
        combined_trace = {
            "provider_attempts": total_attempts,
            "prompt_version": "phase6-codewriter-v1-chunked",
            "action": "final",
            "provider_request_id": last_response.provider_request_id if last_response else None,
            "provider_metadata": {
                **(last_response.provider_metadata if last_response else {}),
                "finish_reason": "stop",
                "chunked": True,
                "chunk_count": len(chunks),
            },
        }
        return combined_output, combined_usage, combined_trace



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
