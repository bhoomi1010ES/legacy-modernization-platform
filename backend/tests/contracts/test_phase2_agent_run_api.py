"""HTTP contract tests for Phase 2 agent-run APIs."""

from fastapi.testclient import TestClient

from app.core.config import settings


def _admin_token(client: TestClient) -> str:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.morgan@acme.corp", "password": "AdminSecure123!"},
    )
    assert response.status_code == 200
    return response.cookies[settings.SESSION_COOKIE_NAME]


def test_fake_agent_run_is_persisted_and_trace_is_readable(client: TestClient):
    token = _admin_token(client)
    jobs = client.get("/api/v1/jobs", cookies={settings.SESSION_COOKIE_NAME: token}).json()["items"]
    assert jobs
    job_id = jobs[0]["job_id"]

    launched = client.post(
        f"/api/v1/jobs/{job_id}/agent-runs",
        cookies={settings.SESSION_COOKIE_NAME: token},
        json={
            "agent_name": "Intake",
            "task_type": "inventory",
            "instruction": "Return a typed fake-model result.",
            "allowed_tools": [],
            "output_schema": {
                "type": "object",
                "properties": {"message": {"type": "string"}, "task_id": {"type": "string"}},
                "required": ["message", "task_id"],
                "additionalProperties": False,
            },
        },
    )
    assert launched.status_code == 201, launched.text
    body = launched.json()
    assert body["status"] == "SUCCEEDED"
    assert body["model_identifier"] == "fake/fake-model-v1"

    listed = client.get(
        f"/api/v1/jobs/{job_id}/agent-runs",
        cookies={settings.SESSION_COOKIE_NAME: token},
    )
    assert listed.status_code == 200
    assert any(item["run_id"] == body["run_id"] for item in listed.json()["items"])

    detail = client.get(
        f"/api/v1/agent-runs/{body['run_id']}",
        cookies={settings.SESSION_COOKIE_NAME: token},
    )
    assert detail.status_code == 200

    trace = client.get(
        f"/api/v1/agent-runs/{body['run_id']}/trace",
        cookies={settings.SESSION_COOKIE_NAME: token},
    )
    assert trace.status_code == 200
    assert trace.json()["status"] == "SUCCEEDED"
    assert trace.json()["output_evidence"]["message"] == "Fake model task completed"


def test_launch_rejects_tool_outside_agent_allowlist(client: TestClient):
    token = _admin_token(client)
    job_id = client.get("/api/v1/jobs", cookies={settings.SESSION_COOKIE_NAME: token}).json()["items"][0]["job_id"]
    response = client.post(
        f"/api/v1/jobs/{job_id}/agent-runs",
        cookies={settings.SESSION_COOKIE_NAME: token},
        json={
            "agent_name": "Intake",
            "instruction": "Attempt an unauthorized mutation.",
            "allowed_tools": ["sandbox_edit"],
        },
    )
    assert response.status_code == 422
    assert "not allowlisted" in response.json()["error"]["message"]
