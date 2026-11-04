"""Persistent, fail-closed accounting for paid provider requests.

The singleton budget row serializes reservations across API processes. A request
left IN_FLIGHT after a crash retains its reservation and cannot be replayed under
the same id; operators must reconcile ambiguous provider outcomes explicitly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Optional

from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.models.model_gateway import ModelGatewayBudget, ModelGatewayRequest
from app.services.model_gateway import ModelGatewayError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PersistentModelRequestLedger:
    async def reserve(
        self,
        *,
        request_id: str,
        provider: str,
        model: str,
        prompt_revision: str,
        amount_usd: float,
        ceiling_usd: float,
        job_id: Optional[str] = None,
        run_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
        selection_hash: Optional[str] = None,
    ) -> None:
        amount = Decimal(str(amount_usd))
        ceiling = Decimal(str(ceiling_usd))
        if not amount.is_finite() or not ceiling.is_finite() or amount <= 0 or ceiling <= 0:
            raise ModelGatewayError("Paid model request needs a positive budget reservation")
        amount = amount.quantize(Decimal('0.000001'), rounding=ROUND_CEILING)
        ceiling = ceiling.quantize(Decimal('0.000001'), rounding=ROUND_FLOOR)
        async with AsyncSessionLocal() as session:
            async with session.begin():
                budget = await session.scalar(
                    select(ModelGatewayBudget)
                    .where(ModelGatewayBudget.budget_id == 1)
                    .with_for_update()
                )
                if budget is None:
                    raise ModelGatewayError(
                        "Persistent model budget migration is not installed; paid request blocked"
                    )
                previous = await session.get(ModelGatewayRequest, request_id)
                if previous is not None:
                    raise ModelGatewayError(
                        "Model request ID is already recorded; duplicate dispatch blocked"
                    )
                effective_ceiling = min(ceiling, Decimal(budget.ceiling_usd))
                if await session.scalar(select(ModelGatewayRequest.request_id).where(ModelGatewayRequest.status == 'OVER_BUDGET').limit(1)):
                    raise ModelGatewayError('An over-budget provider charge requires human reconciliation')
                # Conditional arithmetic is atomic on PostgreSQL and SQLite.
                # SQLite ignores SELECT FOR UPDATE; read/modify/write was unsafe.
                reserved = await session.execute(
                    update(ModelGatewayBudget).where(
                        ModelGatewayBudget.budget_id == 1,
                        ModelGatewayBudget.spent_usd + ModelGatewayBudget.reserved_usd + amount <= effective_ceiling,
                    ).values(
                        reserved_usd=ModelGatewayBudget.reserved_usd + amount,
                        ceiling_usd=effective_ceiling, updated_at=_utcnow(),
                    ).execution_options(synchronize_session=False)
                )
                if reserved.rowcount != 1:
                    raise ModelGatewayError(
                        "Persistent real-model budget cannot reserve the bounded request cost"
                    )
                session.add(
                    ModelGatewayRequest(
                        request_id=request_id,
                        job_id=job_id,
                        run_id=run_id,
                        attempt_id=attempt_id,selection_hash=selection_hash,reconciliation_status='RESERVED',
                        provider=provider,
                        requested_model=model,
                        prompt_revision=prompt_revision,
                        status="RESERVED",
                        reserved_usd=amount,
                    )
                )

    async def begin_attempt(self, request_id: str, *, retry_safe: bool = False) -> int:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                allowed = {'RESERVED', 'RATE_LIMITED'} | ({'IN_FLIGHT'} if retry_safe else set())
                changed = await session.execute(update(ModelGatewayRequest).where(
                    ModelGatewayRequest.request_id == request_id,
                    ModelGatewayRequest.status.in_(allowed),
                ).values(attempt_count=ModelGatewayRequest.attempt_count + 1,
                    status='IN_FLIGHT', last_error_type=None).returning(ModelGatewayRequest.attempt_count))
                count = changed.scalar_one_or_none()
                if count is None:
                    raise ModelGatewayError("Persistent model request is not dispatchable")
                row = await session.get(ModelGatewayRequest, request_id)
                row.started_at = row.started_at or _utcnow()
                return count

    async def record_rate_limit(self, request_id: str) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(update(ModelGatewayRequest).where(
                    ModelGatewayRequest.request_id==request_id,
                    ModelGatewayRequest.status.in_({'RESERVED','IN_FLIGHT','RATE_LIMITED'}),
                ).values(rate_limit_count=ModelGatewayRequest.rate_limit_count+1,status='RATE_LIMITED'))

    async def complete(
        self,
        request_id: str,
        *,
        actual_model: str,
        provider_request_id: Optional[str],
        input_tokens: int,
        output_tokens: int,
        estimated_cost_usd: Optional[float],
        billed_cost_usd: Optional[float],
        charged_cost_usd: float,
    ) -> float:
        charged = Decimal(str(charged_cost_usd))
        if not charged.is_finite() or charged < 0 or input_tokens < 0 or output_tokens < 0:
            raise ModelGatewayError('Invalid provider accounting; reservation retained')
        async with AsyncSessionLocal() as session:
            async with session.begin():
                budget = await session.scalar(
                    select(ModelGatewayBudget)
                    .where(ModelGatewayBudget.budget_id == 1)
                    .with_for_update()
                )
                row = await session.get(ModelGatewayRequest, request_id, with_for_update=True)
                if budget is None or row is None or row.status not in {"IN_FLIGHT", "RATE_LIMITED"}:
                    raise ModelGatewayError("Persistent model request completion has no matching reservation")
                reservation=Decimal(row.reserved_usd)
                changed=await session.execute(update(ModelGatewayRequest).where(
                    ModelGatewayRequest.request_id==request_id,ModelGatewayRequest.status.in_({'IN_FLIGHT','RATE_LIMITED'}),
                ).values(status='OVER_BUDGET' if charged>reservation else 'COMPLETED',actual_model=actual_model,
                    provider_request_id=provider_request_id,input_tokens=input_tokens,output_tokens=output_tokens,
                    estimated_cost_usd=Decimal(str(estimated_cost_usd)) if estimated_cost_usd is not None else None,
                    billed_cost_usd=Decimal(str(billed_cost_usd)) if billed_cost_usd is not None else None,
                    charged_cost_usd=charged,released_usd=max(Decimal('0'),reservation-charged),
                    reconciliation_status='OVER_RESERVATION' if charged>reservation else 'PROVIDER_BILLED' if billed_cost_usd is not None else 'USAGE_ESTIMATE_NOT_BILL',
                    finished_at=_utcnow()).execution_options(synchronize_session=False))
                if changed.rowcount!=1:raise ModelGatewayError('Duplicate or stale model reconciliation rejected')
                total=await session.execute(update(ModelGatewayBudget).where(
                    ModelGatewayBudget.budget_id==1,ModelGatewayBudget.reserved_usd>=reservation,
                ).values(reserved_usd=ModelGatewayBudget.reserved_usd-reservation,
                    spent_usd=ModelGatewayBudget.spent_usd+charged,updated_at=_utcnow())
                    .returning(ModelGatewayBudget.spent_usd).execution_options(synchronize_session=False))
                spent=total.scalar_one_or_none()
                if spent is None:raise ModelGatewayError('Budget reservation accounting mismatch; reconciliation required')
                return float(spent)

    async def fail(self, request_id: str, error_type: str, *, ambiguous: bool) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                # Consistent budget -> request lock order avoids deadlock with
                # reservation and completion in another worker.
                budget = await session.scalar(
                    select(ModelGatewayBudget).where(ModelGatewayBudget.budget_id == 1).with_for_update()
                )
                row = await session.get(ModelGatewayRequest, request_id, with_for_update=True)
                if row is None or row.status in {"COMPLETED", "OVER_BUDGET", "FAILED", "UNKNOWN"}:
                    return
                uncertain=bool(ambiguous and row.attempt_count)
                changed=await session.execute(update(ModelGatewayRequest).where(
                    ModelGatewayRequest.request_id==request_id,ModelGatewayRequest.status.in_({'RESERVED','IN_FLIGHT','RATE_LIMITED'}),
                ).values(status='UNKNOWN' if uncertain else 'FAILED',last_error_type=error_type[:100],finished_at=_utcnow(),
                    reconciliation_status='PROVIDER_RECONCILIATION_REQUIRED' if uncertain else 'RELEASED_UNCHARGED',
                    released_usd=None if uncertain else row.reserved_usd).execution_options(synchronize_session=False))
                if changed.rowcount!=1 or uncertain:return
                released=await session.execute(update(ModelGatewayBudget).where(
                    ModelGatewayBudget.budget_id==1,ModelGatewayBudget.reserved_usd>=row.reserved_usd,
                ).values(reserved_usd=ModelGatewayBudget.reserved_usd-row.reserved_usd,updated_at=_utcnow())
                    .execution_options(synchronize_session=False))
                if released.rowcount!=1:raise ModelGatewayError('Budget release mismatch; reservation retained')


model_request_ledger = PersistentModelRequestLedger()
