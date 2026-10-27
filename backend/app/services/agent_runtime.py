"""Bounded reason-act-observe engine shared by every specialist agent."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Callable, Dict, Optional
from pydantic import ValidationError

from app.schemas.agent_runtime import (
    AgentContext, AgentResult, AgentRunStatus, AgentTask, AgentTrace, AgentTraceStep,
    FailureClassification, ToolCall, ToolResult,
)
from app.services.model_gateway import ModelGateway, ModelNotAllowedError, ModelRetryExhaustedError
from app.services.secret_redactor import SecretRedactor, get_secret_redactor
from app.services.tool_registry import ToolRegistry, validate_json_schema, ToolSchemaError


class AgentRuntime:
    def __init__(self, gateway: ModelGateway, tools: ToolRegistry, *, redactor: Optional[SecretRedactor] = None) -> None:
        self.gateway = gateway
        self.tools = tools
        self.redactor = redactor or get_secret_redactor()

    async def run(
        self,
        task: AgentTask,
        context: AgentContext,
        *,
        cancel_requested: Optional[Callable[[], bool]] = None,
    ) -> AgentResult:
        trace = AgentTrace(
            run_id=context.run_id, job_id=context.job_id, agent_name=context.agent_name,
            correlation_id=context.correlation_id, status=AgentRunStatus.RUNNING,
            model_identifier=f"{task.model_provider}/{task.model_identifier}",
        )
        started = monotonic()
        observations: list[Dict[str, Any]] = []
        output: Optional[Dict[str, Any]] = None
        failure: Optional[FailureClassification] = None
        error: Optional[str] = None

        try:
            for iteration in range(1, task.max_iterations + 1):
                if cancel_requested and cancel_requested():
                    failure, error = FailureClassification.CANCELLED, "Cancellation requested"
                    break
                if monotonic() - started >= task.timeout_seconds:
                    failure, error = FailureClassification.TIMEOUT, "Agent wall-clock timeout exceeded"
                    break
                context.iteration = iteration
                request = self.redactor.redact_object({
                    "task": task.model_dump(mode="json"),
                    "context": context.model_dump(mode="json"),
                    "tools": [s.model_dump(mode="json") for s in self.tools.specs_for(task.allowed_tools)],
                    "observations": observations,
                    "response_contract": {"action": "tool_call|final", "tool_call": "ToolCall|null", "output": "object|null"},
                })
                try:
                    remaining = max(0.001, task.timeout_seconds - (monotonic() - started))
                    gateway_result = await asyncio.wait_for(
                        self.gateway.complete(
                            provider=task.model_provider, model=task.model_identifier,
                            request=request, max_retries=task.model_retries,
                        ), timeout=remaining,
                    )
                except asyncio.TimeoutError:
                    failure, error = FailureClassification.TIMEOUT, "Agent wall-clock timeout exceeded"
                    break
                except ModelRetryExhaustedError as exc:
                    failure, error = FailureClassification.RETRY_EXHAUSTION, str(exc)
                    break
                except ModelNotAllowedError as exc:
                    failure, error = FailureClassification.PERMISSION_DENIED, str(exc)
                    break
                except ValidationError as exc:
                    failure, error = FailureClassification.MALFORMED_OUTPUT, "Model response did not match the structured response contract"
                    break
                response = gateway_result.response
                usage = response.usage
                context.tokens_used += usage.input_tokens + usage.output_tokens
                context.cost_spent_usd += usage.cost_usd
                trace.total_input_tokens += usage.input_tokens
                trace.total_output_tokens += usage.output_tokens
                trace.total_cost_usd += usage.cost_usd
                if context.tokens_used > task.token_budget or context.cost_spent_usd > task.cost_budget_usd:
                    failure, error = FailureClassification.BUDGET_EXHAUSTION, "Agent token or cost budget exhausted"
                    break
                if response.action == "tool_call":
                    call = response.tool_call
                    assert call is not None
                    trace.tool_calls.append(call)
                    trace.steps.append(AgentTraceStep(step_number=len(trace.steps) + 1, step_type="TOOL_CALL", content=self.redactor.redact_object(call.model_dump(mode="json"))))
                    result = await self.tools.execute(call, task=task, context=context, max_output_bytes=task.max_output_bytes)
                    trace.tool_results.append(result)
                    trace.steps.append(AgentTraceStep(step_number=len(trace.steps) + 1, step_type="TOOL_RESULT", content=self.redactor.redact_object(result.model_dump(mode="json")), duration_ms=result.duration_ms))
                    observations.append(result.model_dump(mode="json"))
                    if not result.ok:
                        lowered = (result.error or "").lower()
                        failure = FailureClassification.PERMISSION_DENIED if "not allowed" in lowered or "requires permission" in lowered else FailureClassification.TOOL_ERROR
                        error = result.error
                        break
                    continue
                candidate = response.output
                try:
                    if candidate is None:
                        raise ToolSchemaError("Final output must be a JSON object")
                    encoded = json.dumps(candidate, default=str).encode("utf-8")
                    if len(encoded) > task.max_output_bytes:
                        raise ToolSchemaError("Final output exceeds configured output-size limit")
                    if task.output_schema:
                        validate_json_schema(candidate, task.output_schema)
                    output = self.redactor.redact_object(candidate)
                    trace.steps.append(AgentTraceStep(step_number=len(trace.steps) + 1, step_type="OUTPUT", content=output))
                    break
                except ToolSchemaError as exc:
                    failure, error = FailureClassification.MALFORMED_OUTPUT, str(exc)
                    break
            else:
                failure, error = FailureClassification.ITERATION_EXHAUSTION, "Maximum agent iterations reached"
        except Exception as exc:
            failure, error = FailureClassification.INTERNAL_ERROR, f"Runtime failed: {type(exc).__name__}"

        completed = datetime.now(timezone.utc)
        succeeded = output is not None and failure is None
        status = AgentRunStatus.SUCCEEDED if succeeded else (AgentRunStatus.CANCELLED if failure == FailureClassification.CANCELLED else AgentRunStatus.FAILED)
        trace.status = status
        trace.completed_at = completed
        trace.duration_seconds = monotonic() - started
        trace.failure_classification = failure
        trace.error_message = self.redactor.redact_text(error) if error else None
        return AgentResult(
            run_id=context.run_id, job_id=context.job_id, agent_name=context.agent_name,
            status=status, output_data=output, output_artifacts=[], failure_classification=failure,
            error_message=trace.error_message, trace=trace, input_tokens=trace.total_input_tokens,
            output_tokens=trace.total_output_tokens, cost_usd=trace.total_cost_usd, completed_at=completed,
        )
