"""Contract tests validating OpenAPI specification and standardized API envelopes."""

from fastapi.testclient import TestClient


def test_openapi_schema_generation(client: TestClient):
    """Verifies that the OpenAPI 3.1 specification generates successfully with expected metadata."""
    response = client.get("/openapi.json")
    assert response.status_code == 200, "OpenAPI schema must be accessible."
    schema = response.json()

    assert "openapi" in schema, "Schema must declare OpenAPI version."
    assert schema["info"]["title"] == "Multi-Agent Legacy Code Modernization Platform API"
    assert schema["info"]["version"] == "1.0.0"
    assert "paths" in schema and len(schema["paths"]) > 0, "Schema must contain registered endpoints."


def test_unique_operation_ids(client: TestClient):
    """Ensures that all endpoints have unique, machine-readable operation_ids for SDK generation."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    operation_ids: set[str] = set()
    duplicates: list[str] = []

    for path, methods in schema["paths"].items():
        for method, details in methods.items():
            if method.lower() in {"get", "post", "put", "delete", "patch"}:
                op_id = details.get("operationId")
                assert op_id, f"Endpoint {method.upper()} {path} missing operationId."
                if op_id in operation_ids:
                    duplicates.append(op_id)
                operation_ids.add(op_id)

    assert not duplicates, f"Duplicate operation IDs found: {duplicates}"


def test_api_version_prefix_consistency(client: TestClient):
    """Validates that all business endpoints reside under /api/v1."""
    response = client.get("/openapi.json")
    schema = response.json()

    for path in schema["paths"]:
        assert path.startswith("/api/v1") or path in {"/openapi.json", "/docs", "/redoc"}, (
            f"Endpoint path '{path}' does not conform to /api/v1 versioned prefix."
        )


def test_health_and_readiness_endpoints(client: TestClient):
    """Verifies health and readiness probes respond with 200 OK."""
    health_resp = client.get("/api/v1/health")
    assert health_resp.status_code == 200
    health_data = health_resp.json()
    assert health_data["status"] == "ok"
    assert health_data["database"] == "connected"

    ready_resp = client.get("/api/v1/readiness")
    assert ready_resp.status_code == 200
    ready_data = ready_resp.json()
    assert ready_data["ready"] is True
    assert "database" in ready_data["components"]


def test_standardized_error_envelope_on_validation_failure(client: TestClient):
    """Validates that 422 Unprocessable Entity returns the standardized ErrorEnvelope."""
    # Submit invalid budget < 50.0 and short name < 2 chars
    invalid_payload = {
        "name": "A",
        "source_repository": "https://github.com/acme/invalid",
        "budget": 20.0,
    }
    response = client.post("/api/v1/jobs", json=invalid_payload)
    assert response.status_code == 422
    body = response.json()

    assert "error" in body, "Response must contain 'error' envelope key."
    error = body["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "request_id" in error
    assert isinstance(error.get("details"), list)
    assert len(error["details"]) > 0


def test_standardized_error_envelope_on_not_found(client: TestClient):
    """Validates that 404 Not Found returns the standardized ErrorEnvelope."""
    response = client.get("/api/v1/jobs/JOB-NONEXISTENT")
    assert response.status_code == 404
    body = response.json()

    assert "error" in body
    error = body["error"]
    assert error["code"] == "NOT_FOUND"
    assert "JOB-NONEXISTENT" in error["message"]
    assert "request_id" in error
