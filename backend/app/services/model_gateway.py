"""Provider-neutral model gateway with allowlists, retries, timeouts and accounting."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
import logging
import math
import uuid
from time import monotonic
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional, Protocol

from app.schemas.agent_runtime import ModelResponse, ModelUsage
from app.services.secret_redactor import SecretRedactor, get_secret_redactor

logger = logging.getLogger(__name__)


class ModelLane:
    DETERMINISTIC_FAKE = "deterministic_fake"
    BUDGET_CAPPED_REAL = "budget_capped_real"


class RealModelBudgetTracker:
    _instance: Optional["RealModelBudgetTracker"] = None

    def __init__(self) -> None:
        self.total_spent_usd: float = 0.0
        self.total_calls: int = 0
        self.reserved_usd: float = 0.0
        self._lock = asyncio.Lock()

    async def reserve(self, amount_usd: float, ceiling_usd: float) -> None:
        async with self._lock:
            if self.total_spent_usd >= ceiling_usd:
                raise ModelGatewayError(
                    f"Real model budget ceiling exceeded: spent ${self.total_spent_usd:.4f} >= ${ceiling_usd:.4f}"
                )
            if amount_usd <= 0:
                raise ModelGatewayError(
                    "Real model budget cannot reserve the bounded request cost"
                )
            remaining = max(0.0, ceiling_usd - self.total_spent_usd - self.reserved_usd)
            if amount_usd > remaining:
                raise ModelGatewayError(
                    "Real model budget cannot reserve the bounded request cost"
                )
            self.reserved_usd += amount_usd

    async def reconcile(self, reserved_usd: float, actual_usd: float) -> float:
        async with self._lock:
            self.reserved_usd = max(0.0, self.reserved_usd - reserved_usd)
            self.total_spent_usd += actual_usd
            self.total_calls += 1
            return self.total_spent_usd

    @classmethod
    def get_tracker(cls) -> "RealModelBudgetTracker":
        if cls._instance is None:
            cls._instance = RealModelBudgetTracker()
        return cls._instance

    def record_spend(self, cost_usd: float) -> float:
        self.total_spent_usd += cost_usd
        self.total_calls += 1
        return self.total_spent_usd

    def reset(self) -> None:
        self.total_spent_usd = 0.0
        self.total_calls = 0
        self.reserved_usd = 0.0


class ModelGatewayError(RuntimeError):
    pass


class ModelNotAllowedError(ModelGatewayError):
    pass


class UnchargedModelError(ModelGatewayError):
    """The provider explicitly rejected the request before generation."""
    pass


class ModelRateLimitError(ModelGatewayError):
    pass


class TransientModelError(ModelGatewayError):
    pass


class ModelRetryExhaustedError(ModelGatewayError):
    pass


class ModelProvider(Protocol):
    async def complete(
        self, *, model: str, request: Dict[str, Any]
    ) -> ModelResponse: ...


@dataclass(frozen=True)
class ModelGatewayResult:
    response: ModelResponse
    attempts: int


class FakeModelProvider:
    """Deterministic scripted provider used by CI and local development."""

    def __init__(
        self,
        responses: Optional[
            Iterable[ModelResponse | Dict[str, Any] | Exception]
        ] = None,
        responder: Optional[
            Callable[
                [Dict[str, Any]],
                ModelResponse
                | Dict[str, Any]
                | Awaitable[ModelResponse | Dict[str, Any]],
            ]
        ] = None,
    ) -> None:
        self._responses = deque(responses or [])
        self._responder = responder
        self.requests: list[Dict[str, Any]] = []

    async def complete(self, *, model: str, request: Dict[str, Any]) -> ModelResponse:
        self.requests.append(request)
        value: Any
        if self._responder is not None:
            value = self._responder(request)
            if asyncio.iscoroutine(value):
                value = await value
        elif self._responses:
            value = self._responses.popleft()
        else:
            value = {
                "action": "final",
                "output": {
                    "message": "Fake model task completed",
                    "task_id": request.get("task", {}).get("task_id"),
                },
                "usage": {"input_tokens": 12, "output_tokens": 8, "cost_usd": 0.0},
            }
        if isinstance(value, Exception):
            raise value
        return (
            value
            if isinstance(value, ModelResponse)
            else ModelResponse.model_validate(value)
        )


def _calculate_model_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    m = model.lower()
    if "gpt-4o-mini" in m:
        rate_in, rate_out = 0.15 / 1_000_000, 0.60 / 1_000_000
    elif "gpt-4o" in m:
        rate_in, rate_out = 2.50 / 1_000_000, 10.00 / 1_000_000
    elif "claude-3-5" in m or "claude-3.5" in m:
        rate_in, rate_out = 3.00 / 1_000_000, 15.00 / 1_000_000
    else:
        rate_in, rate_out = 1.00 / 1_000_000, 3.00 / 1_000_000
    return round((input_tokens * rate_in) + (output_tokens * rate_out), 6)


def provider_cost(
    model: str, input_tokens: int, output_tokens: int, usage: dict
) -> tuple[float, str]:
    """Prefer provider-reported billing; explicitly identify an accounting estimate."""
    try:
        value = usage.get("cost")
        if value is not None:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ModelGatewayError("Invalid provider-reported cost")
            return float(value), "provider_reported"
        return (
            _calculate_model_cost(model, input_tokens, output_tokens),
            "estimated_not_provider_billed",
        )
    except Exception:
        logger.exception("provider_cost failed")
        raise


def _estimate_dynamic_reservation(
    model: str,
    request: Dict[str, Any],
    max_cost_usd: Optional[float] = None,
    ceiling_usd: float = 5.0,
) -> float:
    """Calculate bounded reservation dynamically based on requested tokens rather than entire ceiling."""
    if max_cost_usd is not None and max_cost_usd > 0:
        return float(max_cost_usd)
    if request.get("max_cost_usd") is not None and float(request["max_cost_usd"]) > 0:
        return float(request["max_cost_usd"])

    out_tok = request.get("max_output_tokens") or request.get("max_tokens")
    out_tokens = int(out_tok) if out_tok is not None else 2048

    prompt = request.get("prompt") or ""
    messages = request.get("messages") or []
    content_len = len(prompt) + sum(len(str(m.get("content", ""))) for m in messages if isinstance(m, dict))
    task_data = request.get("task")
    if task_data:
        content_len += len(str(task_data))
    in_tokens = max(50, content_len // 4)

    estimated_cost = _calculate_model_cost(model, in_tokens, out_tokens)
    if estimated_cost <= 0:
        estimated_cost = 0.001
    return float(min(estimated_cost, ceiling_usd))


class OpenAIProvider:
    """Invokes models via the OpenAI API directly."""

    def __init__(self, api_key: Optional[str] = None):
        import os
        from app.core.config import settings

        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = getattr(settings, "OPENAI_API_KEY", "") or os.getenv(
                "OPENAI_API_KEY", ""
            )
        self.base_url = "https://api.openai.com/v1"

    async def complete(self, *, model: str, request: Dict[str, Any]) -> ModelResponse:
        import httpx

        if not self.api_key:
            raise ModelGatewayError("OpenAI API key is not configured.")

        messages = request.get("messages", [])
        if not messages and "prompt" in request:
            messages = [{"role": "user", "content": request["prompt"]}]

        payload = {
            "model": model,
            "messages": messages,
            "temperature": request.get("temperature", 0.2),
            "max_tokens": request.get("max_tokens", 8192),
        }
        if "response_format" in request:
            payload["response_format"] = request["response_format"]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Idempotency-Key": str(request.get("_gateway_request_id", "")),
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise TransientModelError(f"OpenAI request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise TransientModelError(f"OpenAI connection error: {exc}") from exc

        if resp.status_code == 401:
            raise UnchargedModelError(
                "OpenAI authentication error (invalid API key)"
            )
        if resp.status_code == 429:
            raise ModelRateLimitError("OpenAI rate limit exceeded")
        if resp.status_code >= 500:
            raise TransientModelError(
                f"OpenAI upstream server error {resp.status_code}"
            )
        if resp.status_code != 200:
            error_type=UnchargedModelError if resp.status_code in {400,401,402,403,404,422} else ModelGatewayError
            raise error_type(f"OpenAI rejected request with HTTP {resp.status_code}")

        data = resp.json()
        choice = data["choices"][0]
        content = choice["message"].get("content", "")
        usage_data = data.get("usage", {})
        usage_reported = isinstance(usage_data, dict) and bool(usage_data)

        in_tok = usage_data.get("prompt_tokens", 0)
        out_tok = usage_data.get("completion_tokens", 0)
        cost, cost_source = provider_cost(model, in_tok, out_tok, usage_data)
        actual_model = data.get("model", model)

        return ModelResponse(
            action="final",
            provider_request_id=data.get("id"),
            provider_metadata={
                "model": data.get("model", model),
                "created": data.get("created"),
                "finish_reason": choice.get("finish_reason"),
                "usage": usage_data,
                "usage_reported": usage_reported,
                "cost_source": cost_source,
            },
            output={"content": content, "raw": choice["message"]},
            usage=ModelUsage(
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_usd=cost,
                reported_input_tokens=in_tok,
                reported_output_tokens=out_tok,
                provider_request_id=data.get("id"),
                provider_model_id=actual_model,
                estimated_cost=cost if cost_source != "provider_reported" else None,
                billed_cost=cost if cost_source == "provider_reported" else None,
            ),
        )


class ModelGateway:
    """Enforces model policy before dispatching to an explicitly registered provider."""

    def __init__(
        self,
        providers: Dict[str, ModelProvider],
        allowlist: Dict[str, set[str]],
        *,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
        requests_per_minute: int = 60,
        redactor: Optional[SecretRedactor] = None,
    ) -> None:
        self.providers = dict(providers)
        self.allowlist = {
            provider: set(models) for provider, models in allowlist.items()
        }
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.requests_per_minute = requests_per_minute
        self.redactor = redactor or get_secret_redactor()
        self._request_times: deque[float] = deque()

    def _check_rate_limit(self) -> None:
        now = monotonic()
        while self._request_times and self._request_times[0] <= now - 60:
            self._request_times.popleft()
        if len(self._request_times) >= self.requests_per_minute:
            raise ModelRateLimitError("Model request rate limit exceeded.")
        self._request_times.append(now)

    async def complete(
        self,
        *,
        provider: str,
        model: str,
        request: Dict[str, Any],
        max_retries: Optional[int] = None,
        lane: Optional[str] = None,
        max_cost_usd: Optional[float] = None,
    ) -> ModelGatewayResult:
        if provider not in self.providers or model not in self.allowlist.get(
            provider, set()
        ):
            raise ModelNotAllowedError(
                f"Provider/model '{provider}/{model}' is not allowlisted."
            )
        is_real_provider = provider == "openai"
        resolved_lane = lane or (
            ModelLane.BUDGET_CAPPED_REAL
            if is_real_provider
            else ModelLane.DETERMINISTIC_FAKE
        )
        is_paid_request = resolved_lane == ModelLane.BUDGET_CAPPED_REAL or is_real_provider
        ledger_context = request.get("ledger_context") or request.get("context") or {}
        run_id = ledger_context.get("run_id")
        iteration = ledger_context.get("iteration", 1)
        request_id = str(
            request.get("request_id")
            or (f"agent-{run_id}-iteration-{iteration}" if run_id else uuid.uuid4())
        )
        if (
            is_paid_request
            and not isinstance(self.providers[provider], FakeModelProvider)
            and not request.get("request_id")
            and not run_id
        ):
            raise ModelGatewayError(
                "Paid model calls require a durable request ID or persisted agent-run identity"
            )
        prompt_revision = str(request.get("prompt_revision") or "unspecified")

        durable_ledger = None
        if is_paid_request:
            from app.core.config import settings

            if not getattr(settings, "REAL_MODEL_SANDBOX_ENABLED", False):
                raise ModelNotAllowedError(
                    "Real model lane is disabled. Unit and CI tests must use the deterministic fake provider lane. "
                    "Set REAL_MODEL_SANDBOX_ENABLED=true and configure MAX_BUDGET_USD to run scheduled real acceptance tests."
                )
        if (
            is_paid_request
            and not isinstance(self.providers[provider], FakeModelProvider)
        ):
            from app.services.model_request_ledger import model_request_ledger

            from app.core.config import settings

            max_budget = getattr(settings, "MAX_BUDGET_USD", 5.0)
            reservation = _estimate_dynamic_reservation(
                model=model,
                request=request,
                max_cost_usd=max_cost_usd,
                ceiling_usd=float(max_budget),
            )
            await model_request_ledger.reserve(
                request_id=request_id,
                provider=provider,
                model=model,
                prompt_revision=prompt_revision,
                amount_usd=reservation,
                ceiling_usd=float(max_budget),
                job_id=ledger_context.get("job_id"),
                run_id=ledger_context.get("run_id"),
                attempt_id=ledger_context.get('attempt_id'),
                selection_hash=ledger_context.get('selection_hash'),
            )
            durable_ledger = model_request_ledger
            tracker = None
        elif resolved_lane == ModelLane.BUDGET_CAPPED_REAL or is_real_provider:
            from app.core.config import settings
            tracker = RealModelBudgetTracker.get_tracker()
            max_budget = getattr(settings, "MAX_BUDGET_USD", 5.0)
            reservation = _estimate_dynamic_reservation(
                model=model,
                request=request,
                max_cost_usd=max_cost_usd,
                ceiling_usd=float(max_budget),
            )
            await tracker.reserve(reservation, float(max_budget))
        else:
            tracker = None
            reservation = 0.0

        sanitized = self.redactor.redact_object(request)
        retries = self.max_retries if max_retries is None else max_retries
        # The provider idempotency key is stable across a retry after an ambiguous
        # timeout. Providers that ignore the header still have a local trace ID.
        sanitized["_gateway_request_id"] = request_id
        sanitized.pop("request_id", None)
        sanitized.pop("prompt_revision", None)
        last_error: Optional[BaseException] = None
        request_attempted = False
        provider_returned = False
        uncertain_charge = False
        # A local request ID alone cannot make a provider retry idempotent. Real
        # providers must explicitly advertise that guarantee before ambiguous
        # failures are retried. Otherwise retain the reservation and escalate.
        provider_retries = retries if getattr(self.providers[provider], "supports_idempotency", False) else (0 if durable_ledger else retries)
        for attempt in range(1, retries + 2):
            try:
                self._check_rate_limit()
            except ModelRateLimitError:
                logger.warning(
                    "model_gateway rate_limited request_id=%s provider=%s model=%s",
                    request_id,
                    provider,
                    model,
                )
                if durable_ledger is not None:
                    await durable_ledger.record_rate_limit(request_id)
                    await durable_ledger.fail(
                        request_id, "ModelRateLimitError", ambiguous=request_attempted and uncertain_charge
                    )
                if tracker is not None and reservation:
                    async with tracker._lock:
                        tracker.reserved_usd = max(0.0, tracker.reserved_usd - reservation)
                raise
            try:
                if durable_ledger is not None:
                    await durable_ledger.begin_attempt(request_id, retry_safe=bool(getattr(self.providers[provider], 'supports_idempotency', False)))
                request_attempted = True
                response = await asyncio.wait_for(
                    self.providers[provider].complete(model=model, request=sanitized),
                    timeout=self.timeout_seconds,
                )
                provider_returned = True
                response = ModelResponse.model_validate(
                    self.redactor.redact_object(response.model_dump())
                )
                meta = dict(response.provider_metadata or {})
                if resolved_lane == ModelLane.BUDGET_CAPPED_REAL or is_real_provider:
                    if durable_ledger is not None and meta.get("usage_reported") is False:
                        await durable_ledger.fail(
                            request_id, "MissingProviderUsage", ambiguous=True
                        )
                        raise ModelGatewayError(
                            "Provider returned no usage; charge remains reserved for reconciliation"
                        )
                    if response.usage:
                        if durable_ledger is not None:
                            total_spent = await durable_ledger.complete(
                                request_id,
                                actual_model=str(meta.get("model") or model),
                                provider_request_id=response.provider_request_id,
                                input_tokens=response.usage.input_tokens,
                                output_tokens=response.usage.output_tokens,
                                estimated_cost_usd=response.usage.estimated_cost,
                                billed_cost_usd=response.usage.billed_cost,
                                charged_cost_usd=response.usage.cost_usd,
                            )
                            if response.usage.cost_usd > reservation:
                                raise ModelGatewayError(
                                    "Actual model charge exceeded its reserved amount; further requests are stopped"
                                )
                        else:
                            total_spent = await tracker.reconcile(
                                reservation, response.usage.cost_usd
                            )
                    elif durable_ledger is not None:
                        await durable_ledger.fail(
                            request_id, "MissingProviderUsage", ambiguous=True
                        )
                        raise ModelGatewayError(
                            "Provider returned no usage; charge remains reserved for reconciliation"
                        )
                    else:
                        raise ModelGatewayError(
                            "Provider returned no usage; paid request cannot be reconciled"
                        )
                    meta["model_lane"] = ModelLane.BUDGET_CAPPED_REAL
                    meta["acceptance_claim_valid"] = True
                    meta["cumulative_spend_usd"] = total_spent
                else:
                    meta["model_lane"] = ModelLane.DETERMINISTIC_FAKE
                    meta["acceptance_claim_valid"] = False
                    meta["audit_note"] = (
                        "Deterministic fake provider; not eligible as real E2E acceptance evidence"
                    )
                response.provider_metadata = meta
                response.provider_metadata.update(
                    request_id=request_id,
                    provider=provider,
                    requested_model=model,
                    actual_model=meta.get("model", model),
                    prompt_revision=prompt_revision,
                    attempts=attempt,
                )
                logger.info(
                    "model_gateway completed request_id=%s provider=%s actual_model=%s prompt_revision=%s attempts=%s input_tokens=%s output_tokens=%s cost_source=%s",
                    request_id,
                    provider,
                    meta.get("model", model),
                    prompt_revision,
                    attempt,
                    response.usage.input_tokens if response.usage else None,
                    response.usage.output_tokens if response.usage else None,
                    meta.get("cost_source"),
                )
                return ModelGatewayResult(response=response, attempts=attempt)
            except (
                asyncio.TimeoutError,
                TransientModelError,
                ModelRateLimitError,
            ) as exc:
                last_error = exc
                rate_limited = isinstance(exc, ModelRateLimitError)
                if rate_limited and durable_ledger is not None:
                    await durable_ledger.record_rate_limit(request_id)
                elif not rate_limited:
                    uncertain_charge = True
                logger.warning(
                    "model_gateway retryable_error request_id=%s provider=%s model=%s attempt=%s error=%s",
                    request_id,
                    provider,
                    model,
                    attempt,
                    type(exc).__name__,
                )
                if attempt > retries or (not rate_limited and attempt > provider_retries):
                    break
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                if durable_ledger is not None:
                    await asyncio.shield(
                        durable_ledger.fail(
                            request_id, "CancelledError", ambiguous=request_attempted
                        )
                    )
                if tracker is not None and reservation:
                    async with tracker._lock:
                        tracker.reserved_usd = max(0.0, tracker.reserved_usd - reservation)
                raise
            except Exception as exc:
                if durable_ledger is not None:
                    await durable_ledger.fail(
                        request_id,
                        type(exc).__name__,
                        ambiguous=request_attempted and not isinstance(exc,UnchargedModelError),
                    )
                if tracker is not None and reservation:
                    async with tracker._lock:
                        tracker.reserved_usd = max(0.0, tracker.reserved_usd - reservation)
                raise
        if durable_ledger is not None:
            await durable_ledger.fail(
                request_id,
                type(last_error).__name__ if last_error else "RequestFailed",
                ambiguous=request_attempted and uncertain_charge,
            )
        if tracker is not None and reservation:
            async with tracker._lock:
                tracker.reserved_usd = max(0.0, tracker.reserved_usd - reservation)
        raise ModelRetryExhaustedError(
            f"Model request failed after {retries + 1} attempts: {type(last_error).__name__}"
        ) from last_error


def build_fake_gateway(provider: Optional[FakeModelProvider] = None) -> ModelGateway:
    return ModelGateway(
        providers={"fake": provider or FakeModelProvider()},
        allowlist={"fake": {"fake-model-v1", "approved-model"}},
        timeout_seconds=5.0,
        max_retries=2,
        requests_per_minute=10_000,
    )


def build_default_gateway() -> ModelGateway:
    from app.core.config import settings

    providers: Dict[str, ModelProvider] = {
        "fake": FakeModelProvider(),
    }
    allowlist: Dict[str, set[str]] = {
        "fake": {"fake-model-v1", "approved-model"},
    }

    if getattr(settings, "OPENAI_API_KEY", ""):
        providers["openai"] = OpenAIProvider(api_key=settings.OPENAI_API_KEY)
        allowlist["openai"] = {
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "o1",
            "o1-preview",
            "o1-mini",
            "o3-mini",
            "gpt-4",
            "gpt-3.5-turbo",
        }

    return ModelGateway(
        providers=providers,
        allowlist=allowlist,
        timeout_seconds=180.0,
        max_retries=2,
        requests_per_minute=60,
    )


class TwoLaneModelRouter:
    """Manages routing between deterministic fake and budget-capped real model lanes."""

    @staticmethod
    def get_lane_gateway(lane: str = ModelLane.DETERMINISTIC_FAKE) -> ModelGateway:
        if lane == ModelLane.DETERMINISTIC_FAKE:
            return build_fake_gateway()
        elif lane == ModelLane.BUDGET_CAPPED_REAL:
            return build_default_gateway()
        else:
            raise ValueError(f"Unknown model lane: {lane}")
