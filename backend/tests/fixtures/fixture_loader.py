"""Fixture loader utility for synthetic reference repositories."""

from pathlib import Path
from typing import Dict, Any
import json

FIXTURES_ROOT = Path(__file__).resolve().parent / "reference_repos"


class ReferenceFixtureLoader:
    @staticmethod
    def get_fixture_path(name: str) -> Path:
        path = FIXTURES_ROOT / name
        if not path.exists():
            raise FileNotFoundError(f"Reference fixture '{name}' not found at {path}")
        return path

    @staticmethod
    def load_fastapi_source() -> Dict[str, str]:
        path = FIXTURES_ROOT / "fastapi_source"
        return {
            "main.py": (path / "main.py").read_text(encoding="utf-8"),
            "requirements.txt": (path / "requirements.txt").read_text(encoding="utf-8"),
        }

    @staticmethod
    def load_django_target() -> Dict[str, str]:
        path = FIXTURES_ROOT / "django_target"
        return {
            "views.py": (path / "views.py").read_text(encoding="utf-8"),
            "serializers.py": (path / "serializers.py").read_text(encoding="utf-8"),
            "requirements.txt": (path / "requirements.txt").read_text(encoding="utf-8"),
        }

    @staticmethod
    def load_static_web_app() -> Dict[str, str]:
        path = FIXTURES_ROOT / "static_web_app"
        return {
            "index.html": (path / "index.html").read_text(encoding="utf-8"),
            "styles.css": (path / "styles.css").read_text(encoding="utf-8"),
            "app.js": (path / "app.js").read_text(encoding="utf-8"),
        }

    @staticmethod
    def load_sql_backed_service() -> Dict[str, str]:
        path = FIXTURES_ROOT / "sql_backed_service"
        return {
            "models.py": (path / "models.py").read_text(encoding="utf-8"),
        }

    @staticmethod
    def load_broken_fixture() -> Dict[str, str]:
        path = FIXTURES_ROOT / "broken_fixture"
        return {
            "syntax_error.py": (path / "syntax_error.py").read_text(encoding="utf-8"),
            "missing_import.py": (path / "missing_import.py").read_text(
                encoding="utf-8"
            ),
        }

    @staticmethod
    def load_slow_worker_fixture() -> Dict[str, str]:
        path = FIXTURES_ROOT / "slow_worker_fixture"
        return {
            "worker.py": (path / "worker.py").read_text(encoding="utf-8"),
        }

    @staticmethod
    def load_malicious_security_fixture() -> Dict[str, Any]:
        path = FIXTURES_ROOT / "malicious_security_fixture" / "vectors.json"
        return json.loads(path.read_text(encoding="utf-8"))
