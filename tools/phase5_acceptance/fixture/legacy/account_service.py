"""Realistic legacy financial account service with balance calculation and side effects."""

import json
from decimal import Decimal
from typing import Any, Dict


class AccountService:
    def __init__(self):
        # In-memory account database simulation for the legacy service
        self.accounts: Dict[int, Dict[str, Any]] = {
            101: {
                "account_id": 101,
                "account_number": "ACC-101-CORP",
                "holder_name": "ACME Industrial Corp",
                "balance": Decimal("1000.00"),
                "status": "ACTIVE",
            },
            102: {
                "account_id": 102,
                "account_number": "ACC-102-RETL",
                "holder_name": "Jane Doe",
                "balance": Decimal("500.00"),
                "status": "ACTIVE",
            },
        }
        self.audit_log = []

    def process_transaction(self, account_id: int, amount: float, transaction_type: str) -> dict:
        if account_id not in self.accounts:
            raise ValueError(f"Account {account_id} not found")
        
        acc = self.accounts[account_id]
        amt = Decimal(str(amount))
        
        if transaction_type == "DEPOSIT":
            acc["balance"] += amt
        elif transaction_type == "WITHDRAWAL":
            if acc["balance"] < amt:
                raise ValueError("Insufficient funds")
            acc["balance"] -= amt
        else:
            raise ValueError(f"Unknown transaction type: {transaction_type}")

        self.audit_log.append({
            "account_id": account_id,
            "action": transaction_type,
            "amount": float(amt),
            "resulting_balance": float(acc["balance"]),
        })

        return {
            "status": "SUCCESS",
            "account_id": account_id,
            "account_number": acc["account_number"],
            "new_balance": float(acc["balance"]),
            "currency": "INR",
        }


service = AccountService()
