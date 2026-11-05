"""Regressions exposed by the real-environment acceptance audit."""

from types import SimpleNamespace
import uuid

import pytest

from app.core.errors import ConflictException
from app.services.integrator_agent import integrator_service
from app.services.model_gateway import ModelGatewayError, provider_cost
from app.services.reviewer_agent import review


@pytest.mark.asyncio
async def test_gateway_retains_provider_identity_usage_and_billing(monkeypatch):
    """Unit-only HTTP double: this is not real-model acceptance evidence."""
    import httpx
    from app.services.model_gateway import OpenAIProvider

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            return httpx.Response(
                200,
                json={
                    "id": "unit-provider-request",
                    "model": "unit-model-version",
                    "created": 123,
                    "choices": [
                        {"message": {"content": "{}"}, "finish_reason": "stop"}
                    ],
                    "usage": {
                        "prompt_tokens": 11,
                        "completion_tokens": 13,
                        "cost": 0.0001,
                    },
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    response = await OpenAIProvider(api_key="unit-only-not-a-real-key").complete(
        model="configured-model", request={"messages": []}
    )
    assert response.provider_request_id == "unit-provider-request"
    assert response.provider_metadata["model"] == "unit-model-version"
    assert response.provider_metadata["cost_source"] == "provider_reported"
    assert response.usage.input_tokens == 11 and response.usage.output_tokens == 13
    assert response.usage.cost_usd == 0.0001


@pytest.mark.parametrize("cost", [0, 0.001234])
def test_provider_billing_is_not_replaced_with_an_estimate(cost):
    assert provider_cost("configured-model", 100, 200, {"cost": cost}) == (
        cost,
        "provider_reported",
    )


def test_missing_provider_billing_is_explicitly_an_estimate():
    assert (
        provider_cost("configured-model", 100, 200, {})[1]
        == "estimated_not_provider_billed"
    )


@pytest.mark.parametrize("cost", [True, -1, float("inf"), float("nan"), "0.01"])
def test_invalid_billing_fails_closed(cost):
    with pytest.raises(ModelGatewayError):
        provider_cost("configured-model", 100, 200, {"cost": cost})


@pytest.mark.asyncio
async def test_integrator_cannot_manufacture_g4_or_bill_fictional_usage():
    class NoWrites:
        def __getattr__(self, name):
            raise AssertionError(
                f"Placeholder integration must not mutate persistence: {name}"
            )

    job = SimpleNamespace(job_id=uuid.uuid4(), status="CONVERTING", budget_used_usd=0)
    with pytest.raises(ConflictException, match="G4 is blocked"):
        await integrator_service.execute_integration(NoWrites(), job)
    assert job.status == "CONVERTING" and job.budget_used_usd == 0


@pytest.mark.parametrize(
    "execution",
    [
        {"available": False},
        {"available": True, "passed": True, "checks": [], "cases": []},
        {
            "available": True,
            "passed": False,
            "checks": [
                {
                    "category": "security",
                    "command": ["bandit"],
                    "status": "FAIL",
                    "artifact_hash": "c" * 64,
                }
            ],
            "cases": [],
        },
    ],
)
def test_reviewer_inspects_execution_not_just_clean_code(execution):
    report = review(
        {"modern/calc.py": "def add(x, y):\n    return x + y\n"},
        [],
        "b" * 64,
        execution=execution,
    )
    assert report["status"] == "REJECTED"
    assert any(
        finding["category"] == "EXECUTION_EVIDENCE" for finding in report["findings"]
    )
