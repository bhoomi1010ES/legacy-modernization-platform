"""Volatile non-semantic output variance normalizer."""

import re
from typing import Any, Dict


class ObservationNormalizer:
    """Replaces non-deterministic volatile tokens (UUIDs, timestamps, paths) with stable placeholders."""

    UUID_REGEX = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
    ISO_TIMESTAMP_REGEX = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\b")
    EPOCH_MS_REGEX = re.compile(r"\b1[6789]\d{11}\b")
    TEMP_PATH_REGEX = re.compile(r"(?:/tmp|/var/folders|C:\\Users\\[^\\]+\\AppData\\Local\\Temp|[A-Za-z]:\\[^ \t\r\n\v\f'\"`]+\\temp)/[^\s'\"`]+", re.IGNORECASE)

    def normalize_text(self, text: str) -> str:
        """Apply deterministic tokenization passes to string text."""
        if not text:
            return ""

        uuid_map: Dict[str, str] = {}
        def _replace_uuid(match):
            val = match.group(0)
            if val not in uuid_map:
                uuid_map[val] = f"<UUID_{len(uuid_map) + 1}>"
            return uuid_map[val]

        res = self.UUID_REGEX.sub(_replace_uuid, text)
        res = self.ISO_TIMESTAMP_REGEX.sub("<TIMESTAMP_1>", res)
        res = self.EPOCH_MS_REGEX.sub("<EPOCH_MS_1>", res)
        res = self.TEMP_PATH_REGEX.sub("<PATH_1>", res)
        return res

    def normalize_data(self, data: Any) -> Any:
        """Recursively normalize dict, list, and string data structures."""
        if isinstance(data, str):
            return self.normalize_text(data)
        elif isinstance(data, dict):
            return {k: self.normalize_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.normalize_data(item) for item in data]
        return data

