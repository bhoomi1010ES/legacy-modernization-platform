from pathlib import Path

gateway_path = Path("backend/app/services/model_gateway.py")
content = gateway_path.read_text(encoding="utf-8")

# Add ModelLane and RealModelBudgetTracker near imports
class_def = '''
class ModelLane:
    DETERMINISTIC_FAKE = "deterministic_fake"
    BUDGET_CAPPED_REAL = "budget_capped_real"


class RealModelBudgetTracker:
    _instance: Optional["RealModelBudgetTracker"] = None

    def __init__(self) -> None:
        self.total_spent_usd: float = 0.0
        self.total_calls: int = 0

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
'''

content = content.replace("class ModelGatewayError(RuntimeError):", class_def + "\nclass ModelGatewayError(RuntimeError):", 1)

# Modify complete signature and body in ModelGateway
old_complete = '''    async def complete(
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
            )'''

new_complete = '''    async def complete(
        self,
        *,
        provider: str,
        model: str,
        request: Dict[str, Any],
        max_retries: Optional[int] = None,
        lane: Optional[str] = None,
    ) -> ModelGatewayResult:
        is_real_provider = provider in ("openai", "openrouter")
        resolved_lane = lane or (ModelLane.BUDGET_CAPPED_REAL if is_real_provider else ModelLane.DETERMINISTIC_FAKE)

        if resolved_lane == ModelLane.BUDGET_CAPPED_REAL or is_real_provider:
            from app.core.config import settings
            if not getattr(settings, "REAL_MODEL_SANDBOX_ENABLED", False):
                raise ModelNotAllowedError(
                    "Real model lane is disabled. Unit and CI tests must use the deterministic fake provider lane. "
                    "Set REAL_MODEL_SANDBOX_ENABLED=true and configure MAX_BUDGET_USD to run scheduled real acceptance tests."
                )
            tracker = RealModelBudgetTracker.get_tracker()
            max_budget = getattr(settings, "MAX_BUDGET_USD", 5.0)
            if tracker.total_spent_usd >= max_budget:
                raise ModelGatewayError(
                    f"Real model budget ceiling exceeded: cumulative spend ${tracker.total_spent_usd:.4f} >= ceiling ${max_budget:.2f}."
                )

        if provider not in self.providers or model not in self.allowlist.get(
            provider, set()
        ):
            raise ModelNotAllowedError(
                f"Provider/model '{provider}/{model}' is not allowlisted."
            )'''

content = content.replace(old_complete, new_complete, 1)

# Modify the return of complete in ModelGateway to set lane metadata
old_return = '''                response = ModelResponse.model_validate(
                    self.redactor.redact_object(response.model_dump())
                )
                return ModelGatewayResult(response=response, attempts=attempt)'''

new_return = '''                response = ModelResponse.model_validate(
                    self.redactor.redact_object(response.model_dump())
                )
                meta = dict(response.provider_metadata or {})
                if resolved_lane == ModelLane.BUDGET_CAPPED_REAL or is_real_provider:
                    tracker = RealModelBudgetTracker.get_tracker()
                    if response.usage:
                        tracker.record_spend(response.usage.cost_usd)
                    meta["model_lane"] = ModelLane.BUDGET_CAPPED_REAL
                    meta["acceptance_claim_valid"] = True
                    meta["cumulative_spend_usd"] = tracker.total_spent_usd
                else:
                    meta["model_lane"] = ModelLane.DETERMINISTIC_FAKE
                    meta["acceptance_claim_valid"] = False
                    meta["audit_note"] = "Deterministic fake provider; not eligible as real E2E acceptance evidence"
                response.provider_metadata = meta
                return ModelGatewayResult(response=response, attempts=attempt)'''

content = content.replace(old_return, new_return, 1)

# Add TwoLaneModelRouter at the end
router_code = '''

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
'''

content += router_code

gateway_path.write_text(content, encoding="utf-8")
print("Updated backend/app/services/model_gateway.py successfully.")

