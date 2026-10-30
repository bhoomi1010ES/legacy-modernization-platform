"""Tests for Stack-Adaptive Characterization Harness (Web/Static UI vs Backend Services)."""

import pytest
import shutil
from pathlib import Path
from unittest.mock import MagicMock
from app.schemas.phase5 import Scenario
from app.services.phase5_engine import (
    is_web_static_project,
    replay,
    replay_web_static,
    resolve_or_create_backend_adapter,
)

BASE_TMP = Path(r"C:\Users\lenovo\Desktop\rebase\backend\tests\temp_workspaces")

@pytest.fixture
def local_tmp_path():
    BASE_TMP.mkdir(parents=True, exist_ok=True)
    import uuid
    sub = BASE_TMP / f"test_{uuid.uuid4().hex[:8]}"
    sub.mkdir()
    yield sub
    shutil.rmtree(sub, ignore_errors=True)


@pytest.mark.asyncio
async def test_detect_web_static_project_by_job_stack():
    job_mock = MagicMock()
    job_mock.source_stack = "HTML / HTML Source Project (None declared)"
    assert is_web_static_project(None, job_mock, None) is True

    job_backend = MagicMock()
    job_backend.source_stack = "Java 8 / Spring Boot"
    assert is_web_static_project(None, job_backend, None) is False


@pytest.mark.asyncio
async def test_detect_web_static_project_by_workspace_files(local_tmp_path: Path):
    # Web project
    (local_tmp_path / "index.html").write_text("<!DOCTYPE html><html><head><title>Test</title></head><body><h1>Hello</h1></body></html>")
    (local_tmp_path / "style.css").write_text("body { color: red; }")
    assert is_web_static_project(local_tmp_path, None, None) is True

    # Backend project with pom.xml
    (local_tmp_path / "pom.xml").write_text("<project></project>")
    assert is_web_static_project(local_tmp_path, None, None) is False


@pytest.mark.asyncio
async def test_replay_web_static_in_memory_double(local_tmp_path: Path):
    html_content = """<!DOCTYPE html>
<html>
<head>
    <title>Alpha97 Car Rental</title>
    <link rel="stylesheet" href="./css/style.css">
    <script src="./js/app.js"></script>
</head>
<body>
    <header id="main-header" class="site-header sticky">
        <h1>Welcome</h1>
    </header>
    <main>
        <img src="./images/car.png" alt="Car">
    </main>
</body>
</html>"""
    (local_tmp_path / "index.html").write_text(html_content, encoding="utf-8")
    
    css_dir = local_tmp_path / "css"
    css_dir.mkdir()
    (css_dir / "style.css").write_text("body { margin: 0; }", encoding="utf-8")

    js_dir = local_tmp_path / "js"
    js_dir.mkdir()
    (js_dir / "app.js").write_text("console.log('ready');", encoding="utf-8")

    images_dir = local_tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "car.png").write_bytes(b"\x89PNG\r\n\x1a\nfakeimage")

    scenario = Scenario(
        name="char_mod_css_test",
        module="mod_css_test",
        interface="main",
        behavior="Verify CSS layout integrity",
    )

    res = await replay(scenario, workspace_path=local_tmp_path)
    assert res["available"] is True
    assert res["execution_mode"] == "IN_MEMORY_DOUBLE"
    assert res["exit_status"] == 0
    assert "output" in res and "side_effects" in res
    output = res["output"]
    assert output["status"] == "PASSED"
    assert output["route_availability"]["accessible"] is True
    assert output["dom_elements"]["title"] == "Alpha97 Car Rental"
    assert "main-header" in output["dom_elements"]["element_ids"]
    assert "site-header" in output["dom_elements"]["classes"]
    assert output["asset_integrity"]["integrity_status"] == "PASS"


@pytest.mark.asyncio
async def test_resolve_or_create_backend_adapter(local_tmp_path: Path):
    scenario = Scenario(
        name="char_service_test",
        module="mod_service",
        interface="api",
        behavior="Service replay",
    )
    # Automatically generates .rebase_adapter.py
    adapter_path = resolve_or_create_backend_adapter(local_tmp_path, None, scenario)
    assert adapter_path is not None
    assert adapter_path.is_file()
    assert adapter_path.name == ".rebase_adapter.py"

    content = adapter_path.read_text(encoding="utf-8")
    assert "Repository-specific legacy adapter" in content
