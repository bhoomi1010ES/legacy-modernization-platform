"""Deterministic Repository Inventory Scanner.

Recursively discovers and inventories source files and project manifests within a cloned workspace.
Enforces:
1. Zero code execution (strictly static inspection).
2. Configurable recursion depth and file-count limits.
3. Explicit exclusions for generated, vendored, and environment directories.
4. Symlink escape protection (preventing symlinks from escaping workspace root).
5. Deterministic language file counts and source byte aggregation.
"""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class DiscoveredManifest:
    """Represents a recognized package manifest or project configuration file."""
    manifest_type: str
    relative_path: str
    absolute_path: Path
    directory_relative: str
    file_size_bytes: int


@dataclass
class LanguageStats:
    """Aggregated source metrics for a detected programming language."""
    name: str
    file_count: int = 0
    byte_count: int = 0
    percentage: float = 0.0


@dataclass
class InventoryResult:
    """Complete, deterministic inventory of a repository snapshot."""
    workspace_root: Path
    total_files_scanned: int = 0
    total_source_bytes: int = 0
    languages: Dict[str, LanguageStats] = field(default_factory=dict)
    manifests: List[DiscoveredManifest] = field(default_factory=list)
    sql_files: List[DiscoveredManifest] = field(default_factory=list)
    migration_dirs: List[str] = field(default_factory=list)
    config_templates: List[DiscoveredManifest] = field(default_factory=list)
    template_files: List[DiscoveredManifest] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    has_source_files: bool = False


class RepositoryInventoryScanner:
    """Scans repository workspace snapshots with strict resource and security bounds."""

    MAX_DEPTH: int = 10
    MAX_FILES: int = 15000
    MAX_FILE_INSPECT_BYTES: int = 2 * 1024 * 1024  # 2 MB per manifest file

    EXCLUDE_DIRS: Set[str] = {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "env",
        ".env",
        "dist",
        "build",
        "target",
        ".build",
        "vendor",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".tox",
        ".idea",
        ".vscode",
        ".gradle",
        "bin",
        "obj",
        "out",
        "coverage",
        ".next",
        ".nuxt",
    }

    # Explicit extension-to-language mapping
    EXTENSION_MAP: Dict[str, str] = {
        ".py": "Python",
        ".pyi": "Python",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".mjs": "JavaScript",
        ".cjs": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".mts": "TypeScript",
        ".cts": "TypeScript",
        ".java": "Java",
        ".kt": "Kotlin",
        ".kts": "Kotlin",
        ".c": "C",
        ".h": "C",
        ".cpp": "C++",
        ".cc": "C++",
        ".cxx": "C++",
        ".hpp": "C++",
        ".hh": "C++",
        ".cs": "C#",
        ".go": "Go",
        ".rs": "Rust",
        ".php": "PHP",
        ".rb": "Ruby",
        ".swift": "Swift",
        ".scala": "Scala",
        ".sh": "Shell",
        ".bash": "Shell",
        ".sql": "SQL",
        ".html": "HTML",
        ".htm": "HTML",
        ".css": "CSS",
        ".scss": "CSS",
        ".sass": "CSS",
        ".less": "CSS",
    }

    # Manifest filenames mapped to canonical manifest types
    MANIFEST_NAMES: Dict[str, str] = {
        "pom.xml": "maven",
        "build.gradle": "gradle",
        "build.gradle.kts": "gradle",
        "package.json": "npm",
        "requirements.txt": "pip",
        "pyproject.toml": "pyproject",
        "pipfile": "pipfile",
        "poetry.lock": "poetry",
        "go.mod": "go",
        "cargo.toml": "cargo",
        "composer.json": "composer",
        "gemfile": "gemfile",
        "package.swift": "swift",
        "dockerfile": "docker",
        "docker-compose.yml": "docker_compose",
        "docker-compose.yaml": "docker_compose",
    }

    MIGRATION_DIR_NAMES: Set[str] = {
        "migrations",
        "migration",
        "alembic",
        "flyway",
        "liquibase",
    }

    CONFIG_TEMPLATE_NAMES: Set[str] = {
        ".env.example",
        ".env.sample",
        ".env.template",
        "database.php",
        "database.default.php",
        "database.yml.example",
        "ormconfig.json",
        "flyway.conf",
    }

    TEMPLATE_SUFFIXES: Set[str] = {
        ".blade.php",
        ".jinja",
        ".jinja2",
        ".twig",
        ".erb",
        ".mustache",
        ".hbs",
    }

    SENSITIVE_PATTERNS: Set[str] = {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        ".env.test",
        "id_rsa",
    }

    @classmethod
    def scan(cls, workspace_path: Path) -> InventoryResult:
        """Deterministically scans a local repository directory."""
        resolved_root = workspace_path.resolve()
        result = InventoryResult(workspace_root=resolved_root)

        if not resolved_root.exists() or not resolved_root.is_dir():
            result.warnings.append(f"Workspace path does not exist or is not a directory: {resolved_root}")
            return result

        file_count = 0
        total_source_bytes = 0
        lang_counters: Dict[str, LanguageStats] = {}

        def _is_safe_path(p: Path) -> bool:
            """Ensures paths and symlinks do not escape the workspace root."""
            try:
                resolved = p.resolve()
                resolved.relative_to(resolved_root)
                return True
            except (ValueError, RuntimeError):
                return False

        # Walk workspace with depth and file limits
        for root, dirs, files in os.walk(str(resolved_root), topdown=True, followlinks=False):
            curr_dir = Path(root)

            # Check symlink escape on current dir
            if not _is_safe_path(curr_dir):
                result.warnings.append(f"Skipping symlink escaping workspace root: {curr_dir.name}")
                dirs.clear()
                continue

            # Calculate relative depth from root
            try:
                rel_dir = curr_dir.relative_to(resolved_root)
                depth = len(rel_dir.parts)
                rel_dir_posix = rel_dir.as_posix()
            except ValueError:
                depth = 0
                rel_dir_posix = ""

            # Check if current directory is a recognized migration directory
            curr_dir_lower = curr_dir.name.lower()
            rel_dir_lower = rel_dir_posix.lower()
            if (
                curr_dir_lower in cls.MIGRATION_DIR_NAMES
                or rel_dir_lower in ("database/migrations", "db/migrate", "prisma/migrations", "db/migrations")
            ):
                if rel_dir_posix and rel_dir_posix not in result.migration_dirs:
                    result.migration_dirs.append(rel_dir_posix)

            # Prune excluded directories
            dirs[:] = [
                d for d in dirs
                if d.lower() not in cls.EXCLUDE_DIRS
                and not d.startswith(".")
                and depth < cls.MAX_DEPTH
            ]

            for filename in sorted(files):
                if file_count >= cls.MAX_FILES:
                    result.warnings.append(
                        f"Scan limit reached: maximum file count of {cls.MAX_FILES} exceeded; scan truncated."
                    )
                    break

                file_path = curr_dir / filename
                if not _is_safe_path(file_path):
                    result.warnings.append(f"Skipping symlink escaping workspace root: {filename}")
                    continue

                lower_name = filename.lower()

                # Safety rule: Never inspect live environment files or private keys
                if (
                    lower_name in cls.SENSITIVE_PATTERNS
                    or lower_name.endswith((".key", ".pem", ".pfx"))
                    or lower_name.startswith("id_rsa")
                ):
                    continue

                try:
                    stat_info = file_path.stat()
                    size_bytes = stat_info.st_size
                except (OSError, PermissionError) as e:
                    result.warnings.append(f"Unreadable file {filename}: {str(e)}")
                    continue

                file_count += 1
                try:
                    rel_file = str(file_path.relative_to(resolved_root)).replace("\\", "/")
                    parent_rel = str(file_path.parent.relative_to(resolved_root)).replace("\\", "/")
                    if parent_rel == ".":
                        parent_rel = ""
                except ValueError:
                    rel_file = filename
                    parent_rel = ""

                suffix = file_path.suffix.lower()

                # Check for manifest matches
                manifest_type = cls.MANIFEST_NAMES.get(lower_name)
                if not manifest_type and lower_name.endswith(".csproj"):
                    manifest_type = "csproj"
                elif not manifest_type and lower_name.endswith(".sln"):
                    manifest_type = "sln"
                elif not manifest_type and "requirements" in lower_name and lower_name.endswith(".txt"):
                    manifest_type = "pip"

                manifest_obj = DiscoveredManifest(
                    manifest_type=manifest_type or "unknown",
                    relative_path=rel_file,
                    absolute_path=file_path,
                    directory_relative=parent_rel,
                    file_size_bytes=size_bytes,
                )

                if manifest_type:
                    result.manifests.append(manifest_obj)

                # Check for SQL schema files
                if suffix == ".sql":
                    result.sql_files.append(
                        DiscoveredManifest(
                            manifest_type="sql",
                            relative_path=rel_file,
                            absolute_path=file_path,
                            directory_relative=parent_rel,
                            file_size_bytes=size_bytes,
                        )
                    )

                # Check for safe configuration templates
                if lower_name in cls.CONFIG_TEMPLATE_NAMES or (
                    lower_name.startswith(".env.") and lower_name in (".env.example", ".env.sample", ".env.template")
                ):
                    result.config_templates.append(
                        DiscoveredManifest(
                            manifest_type="config_template",
                            relative_path=rel_file,
                            absolute_path=file_path,
                            directory_relative=parent_rel,
                            file_size_bytes=size_bytes,
                        )
                    )

                # Check for server-side template files (Blade, Jinja, Twig, etc.)
                if any(lower_name.endswith(ts) for ts in cls.TEMPLATE_SUFFIXES):
                    result.template_files.append(
                        DiscoveredManifest(
                            manifest_type="template",
                            relative_path=rel_file,
                            absolute_path=file_path,
                            directory_relative=parent_rel,
                            file_size_bytes=size_bytes,
                        )
                    )

                # Check for source language match
                lang_name = cls.EXTENSION_MAP.get(suffix)
                if lang_name:
                    total_source_bytes += size_bytes
                    if lang_name not in lang_counters:
                        lang_counters[lang_name] = LanguageStats(name=lang_name)
                    lang_counters[lang_name].file_count += 1
                    lang_counters[lang_name].byte_count += size_bytes

            if file_count >= cls.MAX_FILES:
                break

        result.total_files_scanned = file_count
        result.total_source_bytes = total_source_bytes
        result.has_source_files = total_source_bytes > 0 or len(result.manifests) > 0 or len(result.sql_files) > 0

        # Calculate percentages
        if total_source_bytes > 0:
            for stat in lang_counters.values():
                stat.percentage = round((stat.byte_count / total_source_bytes) * 100, 1)

        result.languages = lang_counters
        return result

