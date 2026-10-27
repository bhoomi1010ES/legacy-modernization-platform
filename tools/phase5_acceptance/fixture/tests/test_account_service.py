"""Legacy unit tests used by ScenarioDiscoveryService to discover behavioral test cases."""

from legacy.account_service import AccountService


def test_deposit_increases_balance():
    svc = AccountService()
    res = svc.process_transaction(101, 250.0, "DEPOSIT")
    assert res["status"] == "SUCCESS"
    assert res["new_balance"] == 1250.0


def test_withdrawal_decreases_balance():
    svc = AccountService()
    res = svc.process_transaction(102, 100.0, "WITHDRAWAL")
    assert res["status"] == "SUCCESS"
    assert res["new_balance"] == 400.0
