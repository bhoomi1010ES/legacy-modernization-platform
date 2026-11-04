from pathlib import Path

test_file = Path("backend/tests/test_w02_isolation_and_ci.py")
content = test_file.read_text(encoding="utf-8")

extra_tests = '''

# ==============================================================================
# 5. Testing Infrastructure Robustness & Edge Cases
# ==============================================================================

@pytest.mark.unit
def test_empty_database_url_refusal():
    """Verify that empty or unparseable database URLs are rejected."""
    with pytest.raises(ProtectedResourceError) as exc_info:
        IsolationGuard.verify_database_url("")
    assert "Empty or unparseable" in str(exc_info.value)


@pytest.mark.unit
def test_invalid_database_name_pattern():
    """Verify that database names with injection characters are rejected."""
    manager = DisposableDatabaseManager()
    with pytest.raises(ValueError) as exc_info:
        manager.create_database("test_db; DROP TABLE users;--")
    assert "Invalid database name" in str(exc_info.value)


@pytest.mark.unit
def test_two_lane_router_dispatch():
    """Verify TwoLaneModelRouter returns the correct gateway and rejects unknown lanes."""
    fake_gw = TwoLaneModelRouter.get_lane_gateway(ModelLane.DETERMINISTIC_FAKE)
    assert "fake" in fake_gw.providers

    real_gw = TwoLaneModelRouter.get_lane_gateway(ModelLane.BUDGET_CAPPED_REAL)
    assert "fake" in real_gw.providers

    with pytest.raises(ValueError) as exc_info:
        TwoLaneModelRouter.get_lane_gateway("unsupported_lane_xyz")
    assert "Unknown model lane" in str(exc_info.value)


@pytest.mark.unit
def test_disposable_db_manager_cleanup_all():
    """Verify cleanup_all handles empty or active databases gracefully without raising."""
    manager = DisposableDatabaseManager()
    manager.active_databases.add("rebase_test_non_existent_mock_db")
    # Must run without crashing
    manager.cleanup_all()
    assert "rebase_test_non_existent_mock_db" not in manager.active_databases
'''

content += extra_tests
test_file.write_text(content, encoding="utf-8")
print("Added extra tests to backend/tests/test_w02_isolation_and_ci.py")

