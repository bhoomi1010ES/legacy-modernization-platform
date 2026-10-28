"""Provider-neutral model gateway with allowlists, retries, timeouts and accounting."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
import logging
import math
from time import monotonic
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional, Protocol

from app.schemas.agent_runtime import ModelResponse, ModelUsage
from app.services.secret_redactor import SecretRedactor, get_secret_redactor

logger = logging.getLogger(__name__)


class ModelGatewayError(RuntimeError):
    pass


class ModelNotAllowedError(ModelGatewayError):
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


class OpenRouterProvider:
    """Invokes models via the OpenRouter API (OpenAI-compatible chat completions)."""

    def __init__(self, api_key: Optional[str] = None):
        import os
        from app.core.config import settings

        self.api_key = (
            api_key
            or getattr(settings, "OPENROUTER_API_KEY", "")
            or os.getenv("OPENROUTER_API_KEY", "")
        )
        self.base_url = "https://openrouter.ai/api/v1"

    async def complete(self, *, model: str, request: Dict[str, Any]) -> ModelResponse:
        import httpx

        if not self.api_key:
            raise ModelGatewayError("OpenRouter API key is not configured.")

        messages = request.get("messages", [])
        if not messages and "prompt" in request:
            messages = [{"role": "user", "content": request["prompt"]}]

        payload = {
            "model": model,
            "messages": messages,
            "temperature": request.get("temperature", 0.2),
            "max_tokens": request.get("max_tokens", 8192),
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://rebase.local",
            "X-Title": "Rebase Legacy Modernization Platform",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            if resp.status_code >= 500:
                raise TransientModelError(
                    f"OpenRouter upstream server error {resp.status_code}"
                )
            if resp.status_code == 429:
                raise ModelRateLimitError("OpenRouter rate limit exceeded")
            if resp.status_code != 200:
                raise ModelGatewayError(
                    f"OpenRouter error {resp.status_code}: {resp.text}"
                )

            data = resp.json()
            choice = data["choices"][0]
            content = choice["message"].get("content", "")
            usage_data = data.get("usage", {})

            in_tok = usage_data.get("prompt_tokens", 0)
            out_tok = usage_data.get("completion_tokens", 0)
            cost, cost_source = provider_cost(model, in_tok, out_tok, usage_data)

            return ModelResponse(
                action="final",
                provider_request_id=data.get("id"),
                provider_metadata={
                    "model": data.get("model"),
                    "created": data.get("created"),
                    "finish_reason": choice.get("finish_reason"),
                    "usage": usage_data,
                    "cost_source": cost_source,
                },
                output={"content": content, "raw": choice["message"]},
                usage=ModelUsage(
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cost_usd=cost,
                ),
            )


class OpenAIProvider:
    """Invokes models via the OpenAI API directly."""

    def __init__(self, api_key: Optional[str] = None):
        import os
        from app.core.config import settings

        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = (
                getattr(settings, "OPENAI_API_KEY", "")
                or os.getenv("OPENAI_API_KEY", "")
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
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
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
            raise ModelGatewayError(f"OpenAI authentication error (invalid API key): {resp.text}")
        if resp.status_code == 429:
            raise ModelRateLimitError("OpenAI rate limit exceeded")
        if resp.status_code >= 500:
            raise TransientModelError(
                f"OpenAI upstream server error {resp.status_code}"
            )
        if resp.status_code != 200:
            raise ModelGatewayError(f"OpenAI error {resp.status_code}: {resp.text}")

        data = resp.json()
        choice = data["choices"][0]
        content = choice["message"].get("content", "")
        usage_data = data.get("usage", {})

        in_tok = usage_data.get("prompt_tokens", 0)
        out_tok = usage_data.get("completion_tokens", 0)
        cost, cost_source = provider_cost(model, in_tok, out_tok, usage_data)

        return ModelResponse(
            action="final",
            provider_request_id=data.get("id"),
            provider_metadata={
                "model": data.get("model", model),
                "created": data.get("created"),
                "finish_reason": choice.get("finish_reason"),
                "usage": usage_data,
                "cost_source": cost_source,
            },
            output={"content": content, "raw": choice["message"]},
            usage=ModelUsage(
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_usd=cost,
            ),
        )


class ModelGateway:
    """Enforces model policy before dispatching to an explicitly registered provider."""

    def __init__(
        self,
        providers: Dict[str, ModelProvider],
        allowlist: Dict[str, set[str]],
        *,
        timeout_seconds: float = 30.0,
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
    ) -> ModelGatewayResult:
        if provider not in self.providers or model not in self.allowlist.get(
            provider, set()
        ):
            raise ModelNotAllowedError(
                f"Provider/model '{provider}/{model}' is not allowlisted."
            )
        sanitized = self.redactor.redact_object(request)
        retries = self.max_retries if max_retries is None else max_retries
        last_error: Optional[BaseException] = None
        for attempt in range(1, retries + 2):
            self._check_rate_limit()
            try:
                response = await asyncio.wait_for(
                    self.providers[provider].complete(model=model, request=sanitized),
                    timeout=self.timeout_seconds,
                )
                response = ModelResponse.model_validate(
                    self.redactor.redact_object(response.model_dump())
                )
                return ModelGatewayResult(response=response, attempts=attempt)
            except (
                asyncio.TimeoutError,
                TransientModelError,
                ModelRateLimitError,
            ) as exc:
                last_error = exc
                if attempt > retries:
                    break
                await asyncio.sleep(0)
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

    if getattr(settings, "OPENROUTER_API_KEY", ""):
        providers["openrouter"] = OpenRouterProvider(
            api_key=settings.OPENROUTER_API_KEY
        )
        allowlist["openrouter"] = {
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "meta-llama/llama-3.3-70b-instruct",
            "qwen/qwen-2.5-coder-32b-instruct",
            "mistralai/mistral-large-2411",
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
        timeout_seconds=60.0,
        max_retries=2,
        requests_per_minute=60,
    )
