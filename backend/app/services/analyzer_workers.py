"""Specialist Analyzer Workers for parallel static inspection and evidence extraction."""

import ast
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from app.schemas.phase4 import (
    AnalysisType,
    AnalyzerWorkerResult,
    ArchitecturalRisk,
    ConfidenceLevel,
    ConfigurationItem,
    DependencyEdge,
    EvidenceRef,
    EvidenceType,
    LegacyModule,
    LegacyTestSuite,
    PersistenceEntity,
    PublicInterface,
    RepositoryInventory,
    WorkerLifecycleStatus,
)
from app.services.evidence_service import evidence_service
from app.services.secret_redactor import get_secret_redactor

logger = logging.getLogger(__name__)


# Prompt injection detection regex patterns
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*instruction\s*:", re.IGNORECASE),
    re.compile(r"ai\s+agent\s*:\s*mark\s+this", re.IGNORECASE),
    re.compile(r"delete\s+the\s+project", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?rules", re.IGNORECASE),
    re.compile(r"override\s+system\s+prompt", re.IGNORECASE),
]


def sanitize_untrusted_text(content: str) -> str:
    """Sanitize repository text treated strictly as untrusted data."""
    try:
        redactor = get_secret_redactor()
        redacted = redactor.redact_text(content)
        return redacted
    except Exception as exc:
        logger.exception("sanitize_untrusted_text failed | %s: %s", type(exc).__name__, exc)
        return content


class BaseAnalyzerWorker:
    """Abstract base worker implementing reason-act-observe static inspection."""

    def __init__(self, analysis_type: AnalysisType):
        self.analysis_type = analysis_type
        self.redactor = get_secret_redactor()

    def run_slice(
        self,
        workspace_path: Path,
        inventory: RepositoryInventory,
        scope: Optional[List[str]] = None,
    ) -> AnalyzerWorkerResult:
        raise NotImplementedError


class StructureModulesWorker(BaseAnalyzerWorker):
    """Analyzes workspace directory layout, packages, and module boundaries."""

    def __init__(self):
        super().__init__(AnalysisType.STRUCTURE_MODULES)

    def run_slice(
        self,
        workspace_path: Path,
        inventory: RepositoryInventory,
        scope: Optional[List[str]] = None,
    ) -> AnalyzerWorkerResult:
        try:
            worker_id = f"worker_struct_{uuid.uuid4().hex[:8]}"
            evidence_list: List[EvidenceRef] = []
            modules: List[Dict[str, Any]] = []
            warnings: List[str] = []

            # 1. Look for Maven/Gradle multi-module pom.xml / settings.gradle
            pom_files = [f for f in inventory.files if f.path.endswith("pom.xml")]
            gradle_files = [f for f in inventory.files if f.path.endswith("build.gradle") or f.path.endswith("build.gradle.kts")]
            package_json_files = [f for f in inventory.files if f.path.endswith("package.json")]
            pyproject_files = [f for f in inventory.files if f.path.endswith("pyproject.toml") or f.path.endswith("setup.py")]

            discovered_roots: Set[str] = set()

            for mf in pom_files + gradle_files + package_json_files + pyproject_files:
                p = Path(mf.path)
                module_dir = p.parent.as_posix()
                discovered_roots.add(module_dir)

            CONTAINER_DIRS = {"apps", "packages", "modules", "services", "src", "components", "libs"}
            NON_CODE_DIRS = {"static", "templates", "assets", "media", "public", "dist", "build", "node_modules", "vendor", ".venv", "venv", "tests", "test", ".git", ".github", "docs"}

            if not discovered_roots:
                all_dirs = set(inventory.directories)
                all_dirs.update(f.path.replace("\\", "/").split("/")[0] for f in inventory.files if "/" in f.path.replace("\\", "/"))
                for d in sorted(all_dirs):
                    parts = d.replace("\\", "/").split("/")
                    if parts[0] in NON_CODE_DIRS:
                        continue
                    if parts[0] in CONTAINER_DIRS:
                        sub_apps = set()
                        for f in inventory.files:
                            f_parts = f.path.replace("\\", "/").split("/")
                            if len(f_parts) >= 3 and f_parts[0] == parts[0] and f_parts[1] not in NON_CODE_DIRS:
                                sub_apps.add(f"{f_parts[0]}/{f_parts[1]}")
                        if sub_apps:
                            discovered_roots.update(sub_apps)
                        else:
                            discovered_roots.add(parts[0])
                    elif len(parts) == 1:
                        has_code = any(
                            f.path.replace("\\", "/").startswith(f"{parts[0]}/") and f.language and f.language not in ("HTML", "CSS", "Markdown")
                            for f in inventory.files
                        )
                        if has_code:
                            discovered_roots.add(parts[0])

            # If only a single generic root was found, inspect natural subdirectories
            # to identify modular component boundaries
            if len(discovered_roots) <= 1:
                sub_packages: Set[str] = set()
                for f in inventory.files:
                    parts = f.path.replace("\\", "/").split("/")
                    if len(parts) >= 3 and parts[0] not in {"tests", "test", ".git", ".github", "docs"}:
                        sub_packages.add(f"{parts[0]}/{parts[1]}")
                    elif len(parts) >= 2 and parts[0] not in {"tests", "test", ".git", ".github", "docs"}:
                        sub_packages.add(parts[0])
                if len(sub_packages) > 1:
                    discovered_roots = sub_packages

            # Ensure all repository files are covered by at least one module.
            # If root files exist outside sub-directories, include '.' (root module).
            if discovered_roots:
                uncovered = [
                    f.path for f in inventory.files
                    if not any(f.path == r or f.path.startswith(f"{r}/") for r in discovered_roots)
                ]
                if uncovered:
                    discovered_roots.add(".")
            else:
                discovered_roots.add(".")

            for mod_path in sorted(discovered_roots):
                mod_name = mod_path if mod_path != "." else Path(workspace_path).name or "root"
                clean_name = mod_name.replace("/", "-").replace("\\", "-")
                mod_id = f"mod_{clean_name}_{uuid.uuid4().hex[:6]}"

                # Collect files in this module ensuring no file is dropped
                if mod_path == ".":
                    if len(discovered_roots) > 1:
                        mod_files = [
                            f.path for f in inventory.files
                            if not any(f.path.startswith(f"{r}/") for r in discovered_roots if r != ".")
                        ]
                    else:
                        mod_files = [f.path for f in inventory.files]
                else:
                    mod_files = [
                        f.path for f in inventory.files
                        if f.path == mod_path or f.path.startswith(f"{mod_path}/")
                    ]

                # Identify language
                langs = [f.language for f in inventory.files if f.path in mod_files and f.language]
                primary_lang = max(set(langs), key=langs.count) if langs else "Unknown"

                # Check for entry points
                entry_points: List[str] = []
                for fp in mod_files:
                    lower = fp.lower()
                    if "main" in lower or "app" in lower or "index" in lower or "server" in lower:
                        entry_points.append(fp)

                ev = evidence_service.create_evidence(
                    source_artifact=inventory.inventory_hash,
                    source_path=mod_path if mod_path != "." else "workspace_root",
                    evidence_type=EvidenceType.FILE_PATH,
                    raw_excerpt=f"Module '{mod_name}' bounded with {len(mod_files)} files.",
                    confidence=ConfidenceLevel.CONFIRMED,
                    agent_name="StructureModulesWorker",
                )
                evidence_list.append(ev)

                modules.append({
                    "module_id": mod_id,
                    "name": clean_name,
                    "path": mod_path,
                    "responsibility": f"Core component for {clean_name}",
                    "language": primary_lang,
                    "entry_points": entry_points[:5],
                    "file_count": len(mod_files),
                    "evidence_refs": [ev.evidence_id],
                })

            result = AnalyzerWorkerResult(
                worker_id=worker_id,
                analysis_type=AnalysisType.STRUCTURE_MODULES,
                input_scope=scope or ["."],
                status=WorkerLifecycleStatus.COMPLETED,
                findings={"modules": modules},
                evidence=evidence_list,
                confidence=ConfidenceLevel.CONFIRMED,
                warnings=warnings,
                model_version="deterministic-structural-scanner",
            )
            return result
        except Exception as exc:
            logger.exception("StructureModulesWorker failed | %s: %s", type(exc).__name__, exc)
            raise


class DependenciesWorker(BaseAnalyzerWorker):
    """Inspects package dependencies, internal imports, and service linkages."""

    def __init__(self):
        super().__init__(AnalysisType.DEPENDENCIES)

    def run_slice(
        self,
        workspace_path: Path,
        inventory: RepositoryInventory,
        scope: Optional[List[str]] = None,
    ) -> AnalyzerWorkerResult:
        try:
            worker_id = f"worker_dep_{uuid.uuid4().hex[:8]}"
            evidence_list: List[EvidenceRef] = []
            edges: List[Dict[str, Any]] = []
            external_deps: List[str] = []

            manifests = [f for f in inventory.files if f.is_manifest]
            for mf in manifests:
                abs_path = workspace_path / mf.path
                if not abs_path.is_file():
                    continue

                try:
                    content = abs_path.read_text(encoding="utf-8", errors="replace")
                    # Check for prompt injection attempts in manifest
                    for pat in PROMPT_INJECTION_PATTERNS:
                        if pat.search(content):
                            logger.warning("Untrusted data flagged prompt injection in manifest: %s", mf.path)

                    if "pom.xml" in mf.path:
                        for artifact_match in re.finditer(r"<artifactId>([^<]+)</artifactId>", content):
                            dep_name = artifact_match.group(1).strip()
                            if dep_name:
                                external_deps.append(f"maven:{dep_name}")
                    elif "package.json" in mf.path:
                        try:
                            pkg_json = json.loads(content)
                            deps = pkg_json.get("dependencies", {})
                            for k in deps:
                                external_deps.append(f"npm:{k}")
                        except Exception:
                            pass
                    elif "requirements.txt" in mf.path:
                        for line in content.splitlines():
                            line = line.strip()
                            if line and not line.startswith("#"):
                                pkg = line.split("==")[0].split(">=")[0].strip()
                                if pkg:
                                    external_deps.append(f"pypi:{pkg}")

                    ev = evidence_service.create_evidence(
                        source_artifact=inventory.inventory_hash,
                        source_path=mf.path,
                        evidence_type=EvidenceType.MANIFEST_ENTRY,
                        raw_excerpt=f"Manifest parsed: {len(external_deps)} dependencies found.",
                        confidence=ConfidenceLevel.CONFIRMED,
                        agent_name="DependenciesWorker",
                    )
                    evidence_list.append(ev)
                except Exception as exc:
                    logger.warning("Failed parsing manifest %s: %s", mf.path, exc)

            result = AnalyzerWorkerResult(
                worker_id=worker_id,
                analysis_type=AnalysisType.DEPENDENCIES,
                input_scope=scope or ["manifests"],
                status=WorkerLifecycleStatus.COMPLETED,
                findings={
                    "dependencies": edges,
                    "external_packages": sorted(list(set(external_deps)))[:100],
                },
                evidence=evidence_list,
                confidence=ConfidenceLevel.CONFIRMED,
                model_version="deterministic-dependency-scanner",
            )
            return result
        except Exception as exc:
            logger.exception("DependenciesWorker failed | %s: %s", type(exc).__name__, exc)
            raise


class PublicInterfacesWorker(BaseAnalyzerWorker):
    """Discovers REST endpoints, public APIs, CLI routes, and controller classes."""

    def __init__(self):
        super().__init__(AnalysisType.PUBLIC_INTERFACES)

    def run_slice(
        self,
        workspace_path: Path,
        inventory: RepositoryInventory,
        scope: Optional[List[str]] = None,
    ) -> AnalyzerWorkerResult:
        try:
            worker_id = f"worker_iface_{uuid.uuid4().hex[:8]}"
            evidence_list: List[EvidenceRef] = []
            interfaces: List[Dict[str, Any]] = []

            # Check source files for REST annotations or routing definitions
            for f in inventory.files:
                if f.is_test or not f.language:
                    continue

                abs_path = workspace_path / f.path
                if not abs_path.is_file() or f.size_bytes > 500_000:
                    continue

                try:
                    text = abs_path.read_text(encoding="utf-8", errors="replace")

                    # Java / Spring REST endpoints
                    if f.language == "Java":
                        for match in re.finditer(
                            r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|RequestMapping)\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']+)[\"']",
                            text,
                        ):
                            http_method = match.group(1).replace("Mapping", "").upper() or "GET"
                            path_val = match.group(2)
                            line_no = text[:match.start()].count("\n") + 1

                            ev = evidence_service.create_evidence(
                                source_artifact=inventory.inventory_hash,
                                source_path=f.path,
                                source_location=f"line {line_no}",
                                evidence_type=EvidenceType.NETWORK_INTERFACE,
                                raw_excerpt=f"Spring {http_method} route: {path_val}",
                                confidence=ConfidenceLevel.CONFIRMED,
                                agent_name="PublicInterfacesWorker",
                            )
                            evidence_list.append(ev)

                            interfaces.append({
                                "interface_id": f"iface_{uuid.uuid4().hex[:8]}",
                                "interface_type": "REST_ENDPOINT",
                                "name": f"{http_method} {path_val}",
                                "signature": match.group(0)[:100],
                                "location_path": f.path,
                                "line_number": line_no,
                                "evidence_refs": [ev.evidence_id],
                            })

                    # Python FastAPI / Flask / Django
                    elif f.language == "Python":
                        # Standard FastAPI / Flask decorators
                        for match in re.finditer(
                            r"@(?:app|router|[A-Za-z0-9_]+)\.(get|post|put|delete|patch|route)\s*\(\s*[\"']([^\"']+)[\"']",
                            text,
                        ):
                            raw_method = match.group(1).upper()
                            http_method = "ANY" if raw_method == "ROUTE" else raw_method
                            path_val = match.group(2)
                            line_no = text[:match.start()].count("\n") + 1

                            ev = evidence_service.create_evidence(
                                source_artifact=inventory.inventory_hash,
                                source_path=f.path,
                                source_location=f"line {line_no}",
                                evidence_type=EvidenceType.NETWORK_INTERFACE,
                                raw_excerpt=f"Python route: {http_method} {path_val}",
                                confidence=ConfidenceLevel.CONFIRMED,
                                agent_name="PublicInterfacesWorker",
                            )
                            evidence_list.append(ev)

                            interfaces.append({
                                "interface_id": f"iface_{uuid.uuid4().hex[:8]}",
                                "interface_type": "REST_ENDPOINT",
                                "name": f"{http_method} {path_val}",
                                "signature": match.group(0)[:100],
                                "location_path": f.path,
                                "line_number": line_no,
                                "evidence_refs": [ev.evidence_id],
                            })

                        # Django URLConf path / re_path / url definitions
                        if f.path.endswith("urls.py") or "urls" in f.path:
                            for match in re.finditer(
                                r"(?:path|re_path|url)\s*\(\s*['\"]([^'\"]*)['\"]\s*,\s*([^,)\s]+)",
                                text,
                            ):
                                path_val = match.group(1)
                                target_view = match.group(2)
                                line_no = text[:match.start()].count("\n") + 1
                                view_lower = target_view.lower()
                                http_method = "POST" if ("create" in view_lower or "submit" in view_lower or "post" in view_lower or "login" in view_lower or "register" in view_lower or "apply" in view_lower) else ("GET" if ("list" in view_lower or "detail" in view_lower or "view" in view_lower or "index" in view_lower) else "ANY")

                                ev = evidence_service.create_evidence(
                                    source_artifact=inventory.inventory_hash,
                                    source_path=f.path,
                                    source_location=f"line {line_no}",
                                    evidence_type=EvidenceType.NETWORK_INTERFACE,
                                    raw_excerpt=f"Django route: {http_method} /{path_val} -> {target_view}",
                                    confidence=ConfidenceLevel.CONFIRMED,
                                    agent_name="PublicInterfacesWorker",
                                )
                                evidence_list.append(ev)

                                interfaces.append({
                                    "interface_id": f"iface_{uuid.uuid4().hex[:8]}",
                                    "interface_type": "REST_ENDPOINT",
                                    "name": f"{http_method} /{path_val.lstrip('/')}",
                                    "signature": match.group(0)[:100],
                                    "location_path": f.path,
                                    "line_number": line_no,
                                    "evidence_refs": [ev.evidence_id],
                                })
                except Exception as exc:
                    logger.warning("Error reading file %s for interfaces: %s", f.path, exc)

            result = AnalyzerWorkerResult(
                worker_id=worker_id,
                analysis_type=AnalysisType.PUBLIC_INTERFACES,
                input_scope=scope or ["source_files"],
                status=WorkerLifecycleStatus.COMPLETED,
                findings={"public_interfaces": interfaces},
                evidence=evidence_list,
                confidence=ConfidenceLevel.CONFIRMED,
                model_version="deterministic-interface-scanner",
            )
            return result
        except Exception as exc:
            logger.exception("PublicInterfacesWorker failed | %s: %s", type(exc).__name__, exc)
            raise


class PersistenceWorker(BaseAnalyzerWorker):
    """Analyzes database connections, ORM models, SQL scripts, and entities."""

    def __init__(self):
        super().__init__(AnalysisType.PERSISTENCE_DATA)

    def run_slice(
        self,
        workspace_path: Path,
        inventory: RepositoryInventory,
        scope: Optional[List[str]] = None,
    ) -> AnalyzerWorkerResult:
        try:
            worker_id = f"worker_persist_{uuid.uuid4().hex[:8]}"
            evidence_list: List[EvidenceRef] = []
            entities: List[Dict[str, Any]] = []

            for f in inventory.files:
                abs_path = workspace_path / f.path
                if not abs_path.is_file() or f.size_bytes > 500_000:
                    continue

                # SQL schema files
                if f.path.endswith(".sql"):
                    try:
                        content = abs_path.read_text(encoding="utf-8", errors="replace")
                        for match in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([`\"\[]?\w+[`\"\]]?)", content, re.IGNORECASE):
                            tbl_name = match.group(1).strip("`\"[]")
                            ev = evidence_service.create_evidence(
                                source_artifact=inventory.inventory_hash,
                                source_path=f.path,
                                evidence_type=EvidenceType.DATABASE_SCHEMA,
                                raw_excerpt=f"SQL table defined: {tbl_name}",
                                confidence=ConfidenceLevel.CONFIRMED,
                                agent_name="PersistenceWorker",
                            )
                            evidence_list.append(ev)
                            entities.append({
                                "entity_id": f"entity_{uuid.uuid4().hex[:8]}",
                                "name": tbl_name,
                                "entity_type": "TABLE",
                                "database_engine": "SQL",
                                "source_path": f.path,
                                "evidence_refs": [ev.evidence_id],
                            })
                    except Exception:
                        pass

                # Java JPA / Hibernate entities
                elif f.language == "Java":
                    try:
                        content = abs_path.read_text(encoding="utf-8", errors="replace")
                        if "@Entity" in content or "@Table" in content:
                            match = re.search(r"class\s+(\w+)", content)
                            if match:
                                entity_name = match.group(1)
                                ev = evidence_service.create_evidence(
                                    source_artifact=inventory.inventory_hash,
                                    source_path=f.path,
                                    evidence_type=EvidenceType.DATABASE_SCHEMA,
                                    raw_excerpt=f"JPA Entity detected: {entity_name}",
                                    confidence=ConfidenceLevel.CONFIRMED,
                                    agent_name="PersistenceWorker",
                                )
                                evidence_list.append(ev)
                                entities.append({
                                    "entity_id": f"entity_{uuid.uuid4().hex[:8]}",
                                    "name": entity_name,
                                    "entity_type": "ORM_MODEL",
                                    "database_engine": "Relational",
                                    "source_path": f.path,
                                    "evidence_refs": [ev.evidence_id],
                                })
                    except Exception:
                        pass

                # Python SQLAlchemy / Django ORM entities
                elif f.language == "Python":
                    try:
                        content = abs_path.read_text(encoding="utf-8", errors="replace")
                        if "__tablename__" in content or "models.Model" in content or "declarative_base" in content or "Base =" in content:
                            for match in re.finditer(r"class\s+(\w+)\s*\(", content):
                                entity_name = match.group(1)
                                if entity_name not in ("Base", "Column"):
                                    tbl_match = re.search(r"__tablename__\s*=\s*['\"]([^'\"]+)['\"]", content)
                                    tbl_name = tbl_match.group(1) if tbl_match else entity_name
                                    ev = evidence_service.create_evidence(
                                        source_artifact=inventory.inventory_hash,
                                        source_path=f.path,
                                        evidence_type=EvidenceType.DATABASE_SCHEMA,
                                        raw_excerpt=f"Python ORM Model detected: {entity_name} ({tbl_name})",
                                        confidence=ConfidenceLevel.CONFIRMED,
                                        agent_name="PersistenceWorker",
                                    )
                                    evidence_list.append(ev)
                                    entities.append({
                                        "entity_id": f"entity_{uuid.uuid4().hex[:8]}",
                                        "name": tbl_name,
                                        "entity_type": "ORM_MODEL",
                                        "database_engine": "Relational",
                                        "source_path": f.path,
                                        "evidence_refs": [ev.evidence_id],
                                    })
                    except Exception:
                        pass

            result = AnalyzerWorkerResult(
                worker_id=worker_id,
                analysis_type=AnalysisType.PERSISTENCE_DATA,
                input_scope=scope or ["schemas", "entities"],
                status=WorkerLifecycleStatus.COMPLETED,
                findings={"persistence_entities": entities},
                evidence=evidence_list,
                confidence=ConfidenceLevel.CONFIRMED,
                model_version="deterministic-persistence-scanner",
            )
            return result
        except Exception as exc:
            logger.exception("PersistenceWorker failed | %s: %s", type(exc).__name__, exc)
            raise


class ConfigurationWorker(BaseAnalyzerWorker):
    """Extracts configuration keys, properties, and flags while shielding secret values."""

    def __init__(self):
        super().__init__(AnalysisType.CONFIGURATION)

    def run_slice(
        self,
        workspace_path: Path,
        inventory: RepositoryInventory,
        scope: Optional[List[str]] = None,
    ) -> AnalyzerWorkerResult:
        try:
            worker_id = f"worker_cfg_{uuid.uuid4().hex[:8]}"
            evidence_list: List[EvidenceRef] = []
            configs: List[Dict[str, Any]] = []

            config_files = [f for f in inventory.files if f.is_config]
            for cf in config_files:
                abs_path = workspace_path / cf.path
                if not abs_path.is_file() or cf.size_bytes > 200_000:
                    continue

                try:
                    content = abs_path.read_text(encoding="utf-8", errors="replace")
                    # Check for prompt injection in config files
                    for pat in PROMPT_INJECTION_PATTERNS:
                        if pat.search(content):
                            logger.warning("Untrusted data flagged prompt injection in config file: %s", cf.path)

                    lines = content.splitlines()
                    for line in lines[:200]:
                        line = line.strip()
                        if not line or line.startswith("#") or line.startswith("//"):
                            continue

                        # Check properties / yaml key: value or key=value
                        key_val = None
                        if "=" in line:
                            parts = line.split("=", 1)
                            key_val = (parts[0].strip(), parts[1].strip())
                        elif ":" in line and not line.startswith("-"):
                            parts = line.split(":", 1)
                            key_val = (parts[0].strip(), parts[1].strip())

                        if key_val:
                            key, val = key_val
                            if len(key) > 60 or " " in key:
                                continue

                            is_secret = any(s in key.lower() for s in {"password", "secret", "token", "apikey", "key", "credential"})
                            ev = evidence_service.create_evidence(
                                source_artifact=inventory.inventory_hash,
                                source_path=cf.path,
                                evidence_type=EvidenceType.CONFIG_KEY,
                                raw_excerpt=f"Config key: {key} (secret_detected={is_secret})",
                                confidence=ConfidenceLevel.CONFIRMED,
                                agent_name="ConfigurationWorker",
                            )
                            evidence_list.append(ev)

                            configs.append({
                                "config_key": key,
                                "config_type": "SECRET_REFERENCE" if is_secret else "FILE_PROPERTY",
                                "source_file": cf.path,
                                "default_value": "[REDACTED]" if is_secret else (val[:50] if val else None),
                                "secret_reference_detected": is_secret,
                                "evidence_refs": [ev.evidence_id],
                            })
                except Exception as exc:
                    logger.warning("Failed reading config %s: %s", cf.path, exc)

            result = AnalyzerWorkerResult(
                worker_id=worker_id,
                analysis_type=AnalysisType.CONFIGURATION,
                input_scope=scope or ["configs"],
                status=WorkerLifecycleStatus.COMPLETED,
                findings={"configurations": configs[:100]},
                evidence=evidence_list,
                confidence=ConfidenceLevel.CONFIRMED,
                model_version="deterministic-config-scanner",
            )
            return result
        except Exception as exc:
            logger.exception("ConfigurationWorker failed | %s: %s", type(exc).__name__, exc)
            raise


class TestsWorker(BaseAnalyzerWorker):
    """Catalogs existing test suites, test frameworks, and coverage relationships."""
    __test__ = False

    def __init__(self):
        super().__init__(AnalysisType.TESTS)

    def run_slice(
        self,
        workspace_path: Path,
        inventory: RepositoryInventory,
        scope: Optional[List[str]] = None,
    ) -> AnalyzerWorkerResult:
        try:
            worker_id = f"worker_test_{uuid.uuid4().hex[:8]}"
            evidence_list: List[EvidenceRef] = []
            suites: List[Dict[str, Any]] = []

            test_files = [f for f in inventory.files if f.is_test]
            test_locations: Set[str] = set()

            for tf in test_files:
                p = Path(tf.path)
                test_locations.add(p.parent.as_posix())

            for loc in sorted(test_locations):
                loc_files = [f for f in test_files if f.path.startswith(f"{loc}/")]
                framework = "native-test-suite"
                for tf in loc_files:
                    try:
                        t_text = (workspace_path / tf.path).read_text(encoding="utf-8", errors="replace")
                        if "junit" in t_text.lower() or "@Test" in t_text:
                            framework = "JUnit"
                            break
                        elif any(k in t_text for k in ["describe(", "it(", "test(", "expect("]):
                            framework = "Jest/Vitest"
                            break
                        elif "pytest" in t_text or "unittest" in t_text:
                            framework = "pytest"
                            break
                    except Exception:
                        pass

                ev = evidence_service.create_evidence(
                    source_artifact=inventory.inventory_hash,
                    source_path=loc,
                    evidence_type=EvidenceType.TEST_CASE,
                    raw_excerpt=f"Test location '{loc}' with {len(loc_files)} test files using {framework}",
                    confidence=ConfidenceLevel.CONFIRMED,
                    agent_name="TestsWorker",
                )
                evidence_list.append(ev)

                suites.append({
                    "suite_id": f"suite_{uuid.uuid4().hex[:8]}",
                    "framework": framework,
                    "test_location": loc,
                    "test_count": len(loc_files),
                    "test_type": "UNIT" if "unit" in loc.lower() else "INTEGRATION",
                    "evidence_refs": [ev.evidence_id],
                })

            result = AnalyzerWorkerResult(
                worker_id=worker_id,
                analysis_type=AnalysisType.TESTS,
                input_scope=scope or ["test_locations"],
                status=WorkerLifecycleStatus.COMPLETED,
                findings={"test_suites": suites},
                evidence=evidence_list,
                confidence=ConfidenceLevel.CONFIRMED,
                model_version="deterministic-test-scanner",
            )
            return result
        except Exception as exc:
            logger.exception("TestsWorker failed | %s: %s", type(exc).__name__, exc)
            raise


class IntegrationExternalWorker(BaseAnalyzerWorker):
    """Detects message queues, external service endpoints, and remote HTTP clients."""

    def __init__(self):
        super().__init__(AnalysisType.INTEGRATION_EXTERNAL)

    def run_slice(
        self,
        workspace_path: Path,
        inventory: RepositoryInventory,
        scope: Optional[List[str]] = None,
    ) -> AnalyzerWorkerResult:
        try:
            worker_id = f"worker_integ_{uuid.uuid4().hex[:8]}"
            evidence_list: List[EvidenceRef] = []
            integrations: List[Dict[str, Any]] = []

            # Check for kafka, rabbitmq, grpc, s3, etc. references in manifests or configs
            keywords = ["kafka", "rabbitmq", "activemq", "redis", "elasticsearch", "s3", "sqs", "sns"]

            for f in inventory.files:
                if not (f.is_config or f.is_manifest):
                    continue
                abs_path = workspace_path / f.path
                if not abs_path.is_file() or f.size_bytes > 200_000:
                    continue

                try:
                    text = abs_path.read_text(encoding="utf-8", errors="replace").lower()
                    for kw in keywords:
                        if kw in text:
                            ev = evidence_service.create_evidence(
                                source_artifact=inventory.inventory_hash,
                                source_path=f.path,
                                evidence_type=EvidenceType.NETWORK_INTERFACE,
                                raw_excerpt=f"External integration reference to '{kw}' detected",
                                confidence=ConfidenceLevel.INFERRED,
                                agent_name="IntegrationExternalWorker",
                            )
                            evidence_list.append(ev)
                            integrations.append({
                                "system": kw,
                                "source_file": f.path,
                                "type": "MESSAGE_BROKER" if kw in {"kafka", "rabbitmq", "activemq"} else "EXTERNAL_SERVICE",
                                "evidence_refs": [ev.evidence_id],
                            })
                except Exception:
                    pass

            result = AnalyzerWorkerResult(
                worker_id=worker_id,
                analysis_type=AnalysisType.INTEGRATION_EXTERNAL,
                input_scope=scope or ["integrations"],
                status=WorkerLifecycleStatus.COMPLETED,
                findings={"integrations": integrations[:50]},
                evidence=evidence_list,
                confidence=ConfidenceLevel.INFERRED,
                model_version="deterministic-integration-scanner",
            )
            return result
        except Exception as exc:
            logger.exception("IntegrationExternalWorker failed | %s: %s", type(exc).__name__, exc)
            raise


class RiskSecurityWorker(BaseAnalyzerWorker):
    """Assesses architectural, dependency, and migration risks with evidence."""

    def __init__(self):
        super().__init__(AnalysisType.RISK_SECURITY)

    def run_slice(
        self,
        workspace_path: Path,
        inventory: RepositoryInventory,
        scope: Optional[List[str]] = None,
    ) -> AnalyzerWorkerResult:
        try:
            worker_id = f"worker_risk_{uuid.uuid4().hex[:8]}"
            evidence_list: List[EvidenceRef] = []
            risks: List[Dict[str, Any]] = []

            # 1. Check for legacy versions (e.g. Java 8 / Python 2)
            has_old_manifest = any("1.8" in f.path or "2.7" in f.path for f in inventory.files)
            if has_old_manifest:
                ev = evidence_service.create_evidence(
                    source_artifact=inventory.inventory_hash,
                    source_path="build-manifest",
                    evidence_type=EvidenceType.STATIC_HEURISTIC,
                    raw_excerpt="End-of-life runtime or legacy language level declared",
                    confidence=ConfidenceLevel.INFERRED,
                    agent_name="RiskSecurityWorker",
                )
                evidence_list.append(ev)
                risks.append({
                    "risk_id": f"risk_{uuid.uuid4().hex[:8]}",
                    "category": "ARCHITECTURAL",
                    "title": "Legacy Runtime Deprecation",
                    "description": "Legacy runtime target requires modernization and library upgrade.",
                    "severity": "HIGH",
                    "inferred": True,
                    "evidence_refs": [ev.evidence_id],
                    "mitigation_suggestion": "Adopt LTS target runtime and verify standard library equivalence.",
                })

            # 2. Check for missing automated tests
            test_count = sum(1 for f in inventory.files if f.is_test)
            if test_count == 0:
                ev = evidence_service.create_evidence(
                    source_artifact=inventory.inventory_hash,
                    source_path="test_locations",
                    evidence_type=EvidenceType.STATIC_HEURISTIC,
                    raw_excerpt="Zero automated tests detected in repository inventory",
                    confidence=ConfidenceLevel.CONFIRMED,
                    agent_name="RiskSecurityWorker",
                )
                evidence_list.append(ev)
                risks.append({
                    "risk_id": f"risk_{uuid.uuid4().hex[:8]}",
                    "category": "TEST",
                    "title": "Zero Test Coverage",
                    "description": "Repository contains zero detected unit or integration tests.",
                    "severity": "CRITICAL",
                    "inferred": False,
                    "evidence_refs": [ev.evidence_id],
                    "mitigation_suggestion": "Gate G2 characterization freeze is mandatory before conversion.",
                })

            # 3. Check for hardcoded secrets, weak crypto, and insecure configurations
            for f in inventory.files:
                if f.is_test or f.size_bytes > 200_000:
                    continue
                abs_path = workspace_path / f.path
                if not abs_path.is_file():
                    continue
                try:
                    content = abs_path.read_text(encoding="utf-8", errors="replace")
                    # Check for weak crypto (MD5/SHA1)
                    if "hashlib.md5" in content or "MD5" in content or 'MessageDigest.getInstance("MD5")' in content:
                        ev = evidence_service.create_evidence(
                            source_artifact=inventory.inventory_hash,
                            source_path=f.path,
                            evidence_type=EvidenceType.CODE_EXCERPT,
                            raw_excerpt=f"Insecure/Weak MD5 hash algorithm usage in {f.path}",
                            confidence=ConfidenceLevel.CONFIRMED,
                            agent_name="RiskSecurityWorker",
                        )
                        evidence_list.append(ev)
                        risks.append({
                            "risk_id": f"risk_{uuid.uuid4().hex[:8]}",
                            "category": "SECURITY",
                            "title": "Weak Cryptographic Hash Detected",
                            "description": f"Use of insecure MD5 hash algorithm detected in {f.path}.",
                            "severity": "HIGH",
                            "inferred": False,
                            "evidence_refs": [ev.evidence_id],
                            "mitigation_suggestion": "Migrate to SHA-256 or bcrypt/Argon2 for passwords.",
                        })

                    # Check for hardcoded credentials / tokens
                    if re.search(r"(?:sk-proj-|AKIA[0-9A-Z]{16}|secret_token\s*=)", content, re.IGNORECASE):
                        ev = evidence_service.create_evidence(
                            source_artifact=inventory.inventory_hash,
                            source_path=f.path,
                            evidence_type=EvidenceType.CODE_EXCERPT,
                            raw_excerpt=f"Hardcoded API credential or secret token pattern detected in {f.path}",
                            confidence=ConfidenceLevel.CONFIRMED,
                            agent_name="RiskSecurityWorker",
                        )
                        evidence_list.append(ev)
                        risks.append({
                            "risk_id": f"risk_{uuid.uuid4().hex[:8]}",
                            "category": "SECURITY",
                            "title": "Hardcoded Secret Reference Detected",
                            "description": f"Potential API key or secret token discovered in source file {f.path}.",
                            "severity": "CRITICAL",
                            "inferred": False,
                            "evidence_refs": [ev.evidence_id],
                            "mitigation_suggestion": "Extract secrets into environment variables and secrets manager.",
                        })
                except Exception:
                    pass

            result = AnalyzerWorkerResult(
                worker_id=worker_id,
                analysis_type=AnalysisType.RISK_SECURITY,
                input_scope=scope or ["risks"],
                status=WorkerLifecycleStatus.COMPLETED,
                findings={"risks": risks},
                evidence=evidence_list,
                confidence=ConfidenceLevel.CONFIRMED,
                model_version="deterministic-risk-scanner",
            )
            return result
        except Exception as exc:
            logger.exception("RiskSecurityWorker failed | %s: %s", type(exc).__name__, exc)
            raise


def execute_worker_slice(
    analysis_type: AnalysisType,
    snapshot_id: str,
    workspace_path: Any,
    file_items: List[Any],
    scope: Optional[List[str]] = None,
) -> AnalyzerWorkerResult:
    """Execute a single specialized analyzer worker slice deterministically."""
    worker_map = {
        AnalysisType.STRUCTURE_MODULES: StructureModulesWorker(),
        AnalysisType.DEPENDENCIES: DependenciesWorker(),
        AnalysisType.PUBLIC_INTERFACES: PublicInterfacesWorker(),
        AnalysisType.PERSISTENCE_DATA: PersistenceWorker(),
        AnalysisType.CONFIGURATION: ConfigurationWorker(),
        AnalysisType.TESTS: TestsWorker(),
        AnalysisType.INTEGRATION_EXTERNAL: IntegrationExternalWorker(),
        AnalysisType.RISK_SECURITY: RiskSecurityWorker(),
    }
    worker = worker_map.get(analysis_type, StructureModulesWorker())
    if isinstance(file_items, RepositoryInventory):
        inv = file_items
    else:
        inv = RepositoryInventory(
            inventory_id=f"inv_{snapshot_id}",
            snapshot_id=snapshot_id,
            job_id="job",
            total_files=len(file_items),
            total_bytes=sum(getattr(f, "size_bytes", 0) for f in file_items),
            files=file_items,
            directories=[],
            inventory_hash="hash",
        )
    return worker.run_slice(
        workspace_path=Path(workspace_path),
        inventory=inv,
        scope=scope,
    )


# Convenient Worker aliases
StructureWorker = StructureModulesWorker
InterfacesWorker = PublicInterfacesWorker
IntegrationWorker = IntegrationExternalWorker
RiskWorker = RiskSecurityWorker

__all__ = [
    "BaseAnalyzerWorker",
    "StructureModulesWorker",
    "StructureWorker",
    "DependenciesWorker",
    "PublicInterfacesWorker",
    "InterfacesWorker",
    "PersistenceWorker",
    "ConfigurationWorker",
    "TestsWorker",
    "IntegrationExternalWorker",
    "IntegrationWorker",
    "RiskSecurityWorker",
    "RiskWorker",
    "execute_worker_slice",
]
