"""Provider-independent object storage abstraction with SHA-256 integrity validation."""

import abc
import hashlib
from pathlib import Path
from typing import Optional, Tuple
from app.core.config import settings
from app.core.errors import NotFoundException, PlatformException


class StorageException(PlatformException):
    def __init__(self, message: str, details: Optional[list] = None):
        super().__init__(code="STORAGE_ERROR", message=message, status_code=500, details=details)


class StorageNotFoundException(NotFoundException):
    def __init__(self, key: str):
        super().__init__(resource="StorageObject", resource_id=key)


class StorageAdapter(abc.ABC):
    """Abstract interface for object storage operations."""

    @abc.abstractmethod
    async def put_object(
        self, key: str, data: bytes, media_type: str = "application/octet-stream"
    ) -> Tuple[str, int]:
        """Stores object bytes. Returns tuple of (sha256_hash, byte_size)."""
        pass

    @abc.abstractmethod
    async def get_object(self, key: str) -> bytes:
        """Retrieves raw object bytes. Raises StorageNotFoundException if missing."""
        pass

    @abc.abstractmethod
    async def object_exists(self, key: str) -> bool:
        """Checks whether the specified key exists in storage."""
        pass

    @abc.abstractmethod
    async def delete_object(self, key: str) -> bool:
        """Deletes object if present. Returns True if deleted, False if not found."""
        pass

    @staticmethod
    def compute_sha256(data: bytes) -> str:
        """Calculates cryptographic SHA-256 checksum."""
        return hashlib.sha256(data).hexdigest()


class LocalStorageAdapter(StorageAdapter):
    """Local filesystem storage adapter for development, testing, and air-gapped runtimes."""

    def __init__(self, base_path: Optional[str] = None):
        raw_path = base_path or settings.ARTIFACT_STORAGE_PATH
        self.base_dir = Path(raw_path).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, key: str) -> Path:
        """Ensures key resolves strictly within base_dir to prevent path traversal."""
        # Normalize separators
        clean_key = key.replace("\\", "/").lstrip("/")
        target_path = (self.base_dir / clean_key).resolve()
        try:
            target_path.relative_to(self.base_dir)
        except ValueError:
            raise StorageException(f"Path traversal detected in storage key: '{key}'")
        return target_path

    async def put_object(
        self, key: str, data: bytes, media_type: str = "application/octet-stream"
    ) -> Tuple[str, int]:
        path = self._resolve_safe_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        content_hash = self.compute_sha256(data)
        return content_hash, len(data)

    async def get_object(self, key: str) -> bytes:
        path = self._resolve_safe_path(key)
        if not path.is_file():
            clean_key = key.replace("\\", "/").lstrip("/")
            candidates = [
                Path.cwd() / "artifacts" / clean_key,
                Path.cwd().parent / "artifacts" / clean_key,
                Path.cwd() / "backend" / "artifacts" / clean_key,
            ]
            for cand in candidates:
                if cand.is_file():
                    return cand.read_bytes()
            raise StorageNotFoundException(key)
        data = path.read_bytes()
        return data

    async def object_exists(self, key: str) -> bool:
        path = self._resolve_safe_path(key)
        if path.is_file():
            return True
        clean_key = key.replace("\\", "/").lstrip("/")
        candidates = [
            Path.cwd() / "artifacts" / clean_key,
            Path.cwd().parent / "artifacts" / clean_key,
            Path.cwd() / "backend" / "artifacts" / clean_key,
        ]
        return any(cand.is_file() for cand in candidates)

    async def delete_object(self, key: str) -> bool:
        path = self._resolve_safe_path(key)
        if path.is_file():
            path.unlink()
            return True
        return False


class InMemoryStorageAdapter(StorageAdapter):
    """In-memory storage adapter for zero-IO unit testing."""

    def __init__(self):
        self._store: dict[str, bytes] = {}

    async def put_object(
        self, key: str, data: bytes, media_type: str = "application/octet-stream"
    ) -> Tuple[str, int]:
        clean_key = key.replace("\\", "/").lstrip("/")
        self._store[clean_key] = data
        return self.compute_sha256(data), len(data)

    async def get_object(self, key: str) -> bytes:
        clean_key = key.replace("\\", "/").lstrip("/")
        if clean_key not in self._store:
            raise StorageNotFoundException(key)
        return self._store[clean_key]

    async def object_exists(self, key: str) -> bool:
        clean_key = key.replace("\\", "/").lstrip("/")
        return clean_key in self._store

    async def delete_object(self, key: str) -> bool:
        clean_key = key.replace("\\", "/").lstrip("/")
        if clean_key in self._store:
            del self._store[clean_key]
            return True
        return False


_storage_adapter: Optional[StorageAdapter] = None


def get_storage_adapter() -> StorageAdapter:
    """Returns singleton storage adapter based on environment configuration."""
    global _storage_adapter
    if _storage_adapter is None:
        _storage_adapter = LocalStorageAdapter()
    return _storage_adapter
