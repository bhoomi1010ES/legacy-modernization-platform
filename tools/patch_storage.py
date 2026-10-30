from pathlib import Path

p = Path("backend/app/core/storage.py")
text = p.read_text(encoding="utf-8")

old_snippet = """    async def get_object(self, key: str) -> bytes:
        path = self._resolve_safe_path(key)
        if not path.is_file():
            raise StorageNotFoundException(key)
        data = path.read_bytes()
        return data

    async def object_exists(self, key: str) -> bool:
        path = self._resolve_safe_path(key)
        return path.is_file()"""

new_snippet = """    async def get_object(self, key: str) -> bytes:
        path = self._resolve_safe_path(key)
        if not path.is_file():
            clean_key = key.replace("\\\\", "/").lstrip("/")
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
        clean_key = key.replace("\\\\", "/").lstrip("/")
        candidates = [
            Path.cwd() / "artifacts" / clean_key,
            Path.cwd().parent / "artifacts" / clean_key,
            Path.cwd() / "backend" / "artifacts" / clean_key,
        ]
        return any(cand.is_file() for cand in candidates)"""

assert old_snippet in text, "old_snippet not found in storage.py"
p.write_text(text.replace(old_snippet, new_snippet, 1), encoding="utf-8")
print("Successfully patched storage.py!")

