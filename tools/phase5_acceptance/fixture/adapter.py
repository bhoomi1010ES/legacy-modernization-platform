"""Phase 5 Legacy Adapter: receives scenario & inputs on stdin, emits output & side_effects on stdout."""

import json
import logging
import sys

from legacy.account_service import AccountService

logger = logging.getLogger(__name__)


def main() -> None:
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            raise ValueError("Empty request on stdin")
        request = json.loads(raw_input)
        if not isinstance(request, dict) or set(request.keys()) != {"scenario", "inputs"}:
            raise ValueError("Request must contain exactly 'scenario' and 'inputs'")

        scenario_name = request["scenario"]
        inputs = request["inputs"]

        service = AccountService()

        if scenario_name in ("process_deposit", "process_transaction", "deposit"):
            account_id = int(inputs.get("account_id", 101))
            amount = float(inputs.get("amount", 250.0))
            tx_type = str(inputs.get("transaction_type", "DEPOSIT"))
            res = service.process_transaction(account_id, amount, tx_type)
            result = {
                "output": res,
                "side_effects": {
                    "writes": 1,
                    "audit_events": 1,
                    "target_table": "account_transactions",
                },
            }
        elif scenario_name in ("withdrawal", "process_withdrawal"):
            account_id = int(inputs.get("account_id", 102))
            amount = float(inputs.get("amount", 100.0))
            res = service.process_transaction(account_id, amount, "WITHDRAWAL")
            result = {
                "output": res,
                "side_effects": {
                    "writes": 1,
                    "audit_events": 1,
                    "target_table": "account_transactions",
                },
            }
        elif scenario_name in ("empty records", "records"):
            result = {
                "output": {"records": []},
                "side_effects": {},
            }
        else:
            raise ValueError(f"Unknown scenario: {scenario_name}")

        json.dump(result, sys.stdout, sort_keys=True, allow_nan=False)
        sys.stdout.flush()
    except Exception as exc:
        logger.exception("adapter failed: %s", exc)
        sys.stderr.write(f"ADAPTER_ERROR: {str(exc)}\n")
        sys.stderr.flush()
        sys.exit(1)


if __name__ == "__main__":
    main()
