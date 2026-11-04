"""Testing infrastructure, disposable database orchestration, and strict isolation guards."""

import atexit
import logging
import os
import re
import secrets
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional, Set
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ProtectedResourceError(RuntimeError):
    """Raised when an operation attempts to mutate or connect to protected persistent resources."""

    pass


class IsolationTokenError(RuntimeError):
    """Raised when an operation is attempted without a valid test isolation token."""

    pass


class IsolationGuard:
    """Enforces strict isolation boundaries between test runners and persistent resources."""

    PROTECTED_DATABASE_NAMES: Set[str] = {
        "rebase",
        "rebase_db",
        "rebase_prod",
        "rebase_dev",
        "rebase_staging",
        "production",
        "prod",
        "staging",
        "main",
    }

    ALLOWED_TEST_PREFIXES: tuple[str, ...] = (
        "rebase_test_",
        "rebase_disposable_",
        "test_",
    )

    @classmethod
    def extract_database_name(cls, database_url: str) -> str:
        """Extract database name safely from SQLAlchemy URL."""
        if not database_url:
            return ""
        parsed = urlparse(database_url.replace("+asyncpg", ""))
        path = parsed.path.lstrip("/")
        return path.split("?")[0].strip()

    @classmethod
    def verify_database_url(
        cls, database_url: str, isolation_token: Optional[str] = None
    ) -> str:
        """Validate that database URL target is disposable and isolated.

        Raises ProtectedResourceError or IsolationTokenError if validation fails.
        """
        db_name = cls.extract_database_name(database_url).lower()
        if not db_name:
            raise ProtectedResourceError(
                "TEST ISOLATION VIOLATION: Empty or unparseable database name."
            )

        if db_name in cls.PROTECTED_DATABASE_NAMES:
            raise ProtectedResourceError(
                f"CRITICAL TEST ISOLATION VIOLATION: Refusing test execution against protected production database '{db_name}'. "
                f"Target URL: {database_url}"
            )

        if not any(marker in db_name for marker in ("test", "disposable", "isolated")):
            raise ProtectedResourceError(
                f"TEST ISOLATION VIOLATION: Database '{db_name}' lacks required test/disposable markers."
            )

        # Enforce token if environment indicates test mode
        active_token = os.getenv("TEST_ISOLATION_TOKEN")
        if active_token is not None:
            if not isolation_token and not active_token:
                raise IsolationTokenError(
                    "TEST ISOLATION VIOLATION: Missing TEST_ISOLATION_TOKEN."
                )
            if isolation_token and isolation_token != active_token:
                raise IsolationTokenError(
                    "TEST ISOLATION VIOLATION: Invalid TEST_ISOLATION_TOKEN provided."
                )

        return db_name

    @classmethod
    def verify_storage_path(cls, storage_path: Path) -> Path:
        """Verify artifact storage path is strictly within disposable temp directories."""
        resolved = storage_path.resolve()
        path_str = str(resolved).lower()
        if any(marker in path_str for marker in ("production", "persistent", "live")):
            raise ProtectedResourceError(
                f"TEST ISOLATION VIOLATION: Storage path points to protected persistent storage: {resolved}"
            )
        return resolved

    @classmethod
    def verify_git_remote(cls, remote_url: str) -> str:
        """Ensure git destinations during test runs are local fixtures or mock remotes."""
        url_lower = remote_url.lower()
        if url_lower.startswith(("http://", "https://", "git@")) and not any(
            h in url_lower for h in ("localhost", "127.0.0.1", "test", "fixture")
        ):
            raise ProtectedResourceError(
                f"TEST ISOLATION VIOLATION: External git remote forbidden during test execution: {remote_url}"
            )
        return remote_url


class DisposableDatabaseManager:
    """Provisions and destroys disposable PostgreSQL test databases per run."""

    def __init__(
        self,
        admin_url: Optional[str] = None,
        db_prefix: str = "rebase_test_",
    ):
        self.admin_url = admin_url or os.getenv(
            "POSTGRES_ADMIN_URL",
            "postgresql://postgres:postres123@localhost:5432/postgres",
        )
        self.db_prefix = db_prefix
        self.active_databases: Set[str] = set()
        atexit.register(self.cleanup_all)

    def generate_database_name(self) -> str:
        unique_suffix = uuid.uuid4().hex[:12]
        return f"{self.db_prefix}{unique_suffix}"

    def generate_isolation_token(self) -> str:
        token = secrets.token_hex(16)
        os.environ["TEST_ISOLATION_TOKEN"] = token
        return token

    def create_database(self, db_name: Optional[str] = None) -> str:
        """Creates an isolated PostgreSQL database for test execution."""
        import psycopg2

        if not db_name:
            db_name = self.generate_database_name()

        # Enforce name safety
        if not re.match(r"^[a-zA-Z0-9_]+$", db_name):
            raise ValueError(f"Invalid database name: {db_name}")

        IsolationGuard.verify_database_url(
            f"postgresql://dummy:dummy@localhost:5432/{db_name}"
        )

        conn = psycopg2.connect(self.admin_url)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(f'CREATE DATABASE "{db_name}"')
            self.active_databases.add(db_name)
            logger.info("Created disposable test database: %s", db_name)
        finally:
            conn.close()

        return db_name

    def run_migrations(self, db_name: str, backend_dir: Optional[Path] = None) -> None:
        """Executes Alembic migrations against the disposable database."""
        if not backend_dir:
            backend_dir = Path(__file__).resolve().parent.parent.parent

        async_url = f"postgresql+asyncpg://postgres:postres123@localhost:5432/{db_name}"
        env = os.environ.copy()
        env["DATABASE_URL"] = async_url
        env["ENVIRONMENT"] = "testing"

        res = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(backend_dir),
            env=env,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(
                f"Alembic migration failed on disposable database '{db_name}':\n"
                f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"
            )
        logger.info("Successfully ran Alembic migrations on %s", db_name)

    def drop_database(self, db_name: str) -> None:
        """Terminates active connections and drops the disposable database."""
        import psycopg2

        if db_name not in self.active_databases and not db_name.startswith(
            self.db_prefix
        ):
            logger.warning(
                "Skipping drop of unmanaged or non-test database: %s", db_name
            )
            return

        conn = psycopg2.connect(self.admin_url)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = %s AND pid <> pg_backend_pid()
                    """,
                    (db_name,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
            self.active_databases.discard(db_name)
            logger.info("Successfully dropped disposable test database: %s", db_name)
        except Exception as exc:
            logger.error("Error dropping disposable database %s: %s", db_name, exc)
        finally:
            conn.close()

    def cleanup_all(self) -> None:
        """Cleanup all managed disposable test databases."""
        for db_name in list(self.active_databases):
            try:
                self.drop_database(db_name)
            except Exception:
                pass


# Global singleton instance for test fixtures
disposable_db_manager = DisposableDatabaseManager()
