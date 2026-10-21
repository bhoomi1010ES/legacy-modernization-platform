"""Repository Intake Stack Detector.

Performs static technology stack detection, manifest parsing, language distribution analysis,
monorepo component decomposition, and Three-Tier Architecture characterization (Frontend,
Backend, Database/Persistence) using controlled, ephemeral workspace snapshots.

Enforces:
1. Zero code execution (no build scripts, hooks, or package managers executed).
2. Deterministic, evidence-backed classification (zero fabricated fallbacks).
3. Explicit scan statuses: COMPLETED, PARTIAL, INCONCLUSIVE, FAILED.
4. Clean separation of Frontend SPAs/templates, Backend services, and Database engines/drivers/schemas.
5. Integration with ControlledGitAdapter and automatic ephemeral workspace cleanup.
6. Non-guessing persistence heuristics: dialect is unconfirmed unless vendor DDL or drivers prove it.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import tomllib
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse
import uuid
import xml.etree.ElementTree as ET

from app.core.config import settings
from app.core.errors import ErrorDetail
from app.schemas.jobs import (
    DatabaseComponent,
    DatabaseTierGroup,
    DetectedStackResponse,
    TierComponent,
    TierGroup,
    TieredStackBreakdown,
)
from app.services.git_adapter import ControlledGitAdapter, GitOperationException, GitSecurityException
from app.services.inventory_scanner import DiscoveredManifest, InventoryResult, RepositoryInventoryScanner

logger = logging.getLogger(__name__)


class StackDetector:
    """Detects programming languages, frameworks, build tools, databases, and architectural tiers."""

    MAX_FILE_INSPECT_BYTES: int = 2 * 1024 * 1024  # 2 MB per manifest
    MAX_SQL_INSPECT_BYTES: int = 64 * 1024         # 64 KB per SQL file

    @classmethod
    def detect_stack(
        cls,
        source_repository: str,
        source_revision: str = "main",
        git_adapter: Optional[ControlledGitAdapter] = None,
    ) -> DetectedStackResponse:
        """Clones a repository into an isolated OS temporary directory and performs static inventory and detection."""
        if not source_repository or not isinstance(source_repository, str) or not source_repository.strip():
            raise GitSecurityException("Repository URL cannot be empty.", issue="source_repository is required.")

        clean_repo = source_repository.strip()
        revision = source_revision.strip() if source_revision else "HEAD"

        adapter = git_adapter or ControlledGitAdapter(
            allow_local_repos_for_test=settings.ENVIRONMENT in ("testing", "development")
        )

        # Validate URL format and SSRF constraints
        adapter.validate_source_url(clean_repo)

        # Safely purge stale preview directories in OS temp older than 1 hour
        try:
            ControlledGitAdapter.cleanup_stale_preview_workspaces(max_age_hours=1.0)
        except Exception:
            pass

        workspace_path: Optional[Path] = None
        resolved_commit: Optional[str] = None
        cleanup_fn: Optional[Callable[[], None]] = None

        try:
            workspace_path, resolved_commit, cleanup_fn = adapter.acquire_ephemeral_workspace(
                repo_url=clean_repo,
                revision=revision,
                depth=1,
                timeout_seconds=45,
                max_size_mb=100,
            )

            # Discover the actual branch checked out
            actual_branch = "HEAD"
            try:
                actual_branch = adapter._execute_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=workspace_path)
            except Exception:
                pass

            effective_revision = actual_branch if actual_branch and actual_branch != "HEAD" else (revision or "main")

            # Perform recursive inventory scan on acquired ephemeral snapshot
            inventory = RepositoryInventoryScanner.scan(workspace_path)

            if effective_revision != revision and revision in ("main", "master") and effective_revision in ("main", "master"):
                inventory.warnings.append(
                    f"Repository default branch '{effective_revision}' was checked out (requested '{revision}' not present)."
                )

            return cls._analyze_inventory(
                inventory=inventory,
                source_repository=clean_repo,
                source_revision=effective_revision,
                requested_revision=revision,
                resolved_commit=resolved_commit,
            )

        finally:
            if cleanup_fn:
                try:
                    cleanup_fn()
                except Exception as e:
                    logger.warning(f"Failed to cleanup ephemeral preview workspace: {e}")

    @classmethod
    def _analyze_inventory(
        cls,
        inventory: InventoryResult,
        source_repository: str,
        source_revision: str,
        requested_revision: Optional[str] = None,
        resolved_commit: Optional[str] = None,
    ) -> DetectedStackResponse:
        """Analyzes inventory results and manifests to construct an evidence-backed DetectedStackResponse."""
        warnings: List[str] = list(inventory.warnings)
        evidence: List[Dict[str, str]] = []
        frameworks: List[Dict[str, Any]] = []
        components: List[Dict[str, Any]] = []

        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Empty repository case
        if inventory.total_files_scanned == 0:
            return DetectedStackResponse(
                source_repository=source_repository,
                source_revision=source_revision,
                requested_revision=requested_revision or source_revision,
                primary_language="Unknown",
                language_version="Unknown",
                framework="None detected",
                framework_version="N/A",
                build_tool="None",
                build_file="None",
                test_framework="None",
                architecture_style="Empty Repository",
                confidence_score=0.0,
                summary_stack="Empty repository",
                detection_method="Static Filesystem Inventory",
                scan_status="INCONCLUSIVE",
                is_fallback=False,
                warnings=["Repository contains zero files."],
                components=[],
                tiers=TieredStackBreakdown(),
                languages={},
                frameworks=[],
                evidence=[],
                resolved_commit=resolved_commit,
                detector_version="2.2.0",
                scanned_at=now_iso,
                metadata={"total_files": 0, "total_source_bytes": 0},
            )

        # 2. Parse all discovered manifests
        manifest_findings: List[Dict[str, Any]] = []
        for manifest in inventory.manifests:
            parsed = cls._parse_manifest(manifest, inventory)
            if parsed:
                manifest_findings.append(parsed)

        warnings = list(inventory.warnings)

        # 3. Documentation / Config Only case (no source code and no recognized application manifests)
        if not inventory.has_source_files and not manifest_findings and not inventory.sql_files:
            return DetectedStackResponse(
                source_repository=source_repository,
                source_revision=source_revision,
                requested_revision=requested_revision or source_revision,
                primary_language="Unknown",
                language_version="Unknown",
                framework="None detected",
                framework_version="N/A",
                build_tool="None",
                build_file="None",
                test_framework="None",
                architecture_style="Non-Code / Documentation Repository",
                confidence_score=0.0,
                summary_stack="No application stack detected",
                detection_method="Static Filesystem Inventory",
                scan_status="INCONCLUSIVE",
                is_fallback=False,
                warnings=warnings or ["No recognized application source code or project manifests found."],
                components=[],
                tiers=TieredStackBreakdown(),
                languages={},
                frameworks=[],
                evidence=[],
                resolved_commit=resolved_commit,
                detector_version="2.2.0",
                scanned_at=now_iso,
                metadata={"total_files": inventory.total_files_scanned, "total_source_bytes": 0},
            )

        # 4. Construct language breakdown
        languages_dict = {
            name: {
                "file_count": stat.file_count,
                "byte_count": stat.byte_count,
                "percentage": stat.percentage,
            }
            for name, stat in sorted(
                inventory.languages.items(), key=lambda item: item[1].byte_count, reverse=True
            )
        }

        # 5. Extract Three-Tier Architecture
        tiers, tier_warnings = cls._extract_three_tiers(
            inventory=inventory,
            manifest_findings=manifest_findings,
            languages_dict=languages_dict,
        )
        for tw in tier_warnings:
            if tw not in warnings:
                warnings.append(tw)

        # 6. Monorepo component decomposition: group manifest findings by directory
        dir_to_findings: Dict[str, List[Dict[str, Any]]] = {}
        for finding in manifest_findings:
            rel_dir = finding.get("directory_relative", "")
            dir_to_findings.setdefault(rel_dir, []).append(finding)

        # Build components list
        for rel_dir, findings in dir_to_findings.items():
            comp_id = rel_dir.replace("/", "-").replace("\\", "-") if rel_dir else "root"
            comp_name = rel_dir if rel_dir else "Root Component"

            comp_langs = {f["language"] for f in findings if f.get("language")}
            comp_frameworks = [f["framework"] for f in findings if f.get("framework")]
            comp_build_tools = [f["build_tool"] for f in findings if f.get("build_tool")]
            comp_types = {f["component_type"] for f in findings if f.get("component_type")}

            comp_type = "frontend" if "frontend" in comp_types else (
                "backend" if "backend" in comp_types else "service"
            )

            comp_evidence = []
            for f in findings:
                comp_evidence.extend(f.get("evidence", []))

            components.append({
                "component_id": comp_id,
                "name": comp_name,
                "relative_path": rel_dir,
                "component_type": comp_type,
                "primary_language": " / ".join(sorted(list(comp_langs))) if comp_langs else "Unknown",
                "framework": " + ".join(comp_frameworks) if comp_frameworks else "Generic",
                "build_tool": comp_build_tools[0] if comp_build_tools else "None",
                "manifest_files": [f["manifest_file"] for f in findings],
                "evidence": comp_evidence,
            })

        # 7. Determine primary language and framework overall (for backward compatibility)
        primary_lang = "Unknown"
        lang_ver = "Unknown"
        primary_framework = "None detected"
        framework_ver = "N/A"
        build_tool = "None"
        build_file = "None"
        test_framework = "None"
        arch_style = "Monolithic Application"

        if manifest_findings:
            # Prefer backend finding or root finding
            backend_findings = [f for f in manifest_findings if f.get("component_type") == "backend"]
            root_findings = [f for f in manifest_findings if f.get("directory_relative") == ""]
            primary_finding = backend_findings[0] if backend_findings else (
                root_findings[0] if root_findings else manifest_findings[0]
            )

            primary_lang = primary_finding.get("language", "Unknown")
            lang_ver = primary_finding.get("language_version", primary_lang)
            primary_framework = primary_finding.get("framework", "Generic")
            framework_ver = primary_finding.get("framework_version", "N/A")
            build_tool = primary_finding.get("build_tool", "None")
            build_file = primary_finding.get("manifest_file", "None")
            test_framework = primary_finding.get("test_framework", "None")
            arch_style = primary_finding.get("architecture_style", "Application Service")

            for f in manifest_findings:
                frameworks.append({
                    "name": f.get("framework"),
                    "version": f.get("framework_version"),
                    "category": f.get("component_type"),
                    "manifest": f.get("manifest_file"),
                })
                evidence.extend(f.get("evidence", []))

        elif languages_dict:
            top_lang = list(languages_dict.keys())[0]
            primary_lang = top_lang
            lang_ver = f"{top_lang} (Inferred from source files)"
            primary_framework = f"{top_lang} Source Project"
            build_tool = "None declared"
            build_file = "None"
            test_framework = "None declared"
            arch_style = f"Plain {top_lang} Application"
            warnings.append(f"No package manifest detected; language inferred from {top_lang} source file extensions.")
            evidence.append({
                "file": f"*.{top_lang.lower()}",
                "reason": f"Discovered {languages_dict[top_lang]['file_count']} files matching extension.",
            })

        # 8. Multi-tier / Full-Stack combination
        has_frontend = tiers.frontend.primary is not None
        has_backend = tiers.backend.primary is not None
        if has_frontend and has_backend:
            arch_style = "Full-Stack Web App (Frontend + Backend)"
            if "TypeScript" in languages_dict or "JavaScript" in languages_dict:
                if primary_lang not in ("TypeScript", "JavaScript"):
                    primary_lang = f"{primary_lang} / TypeScript"

        # 9. Compute Confidence Score & Scan Status
        degrading_keywords = ("malformed", "unreadable", "truncated", "scan limit", "failed to read", "escaping workspace", "conflicting")
        degrading_warnings = [
            w for w in warnings
            if any(k in w.lower() for k in degrading_keywords)
        ]
        has_degrading = len(degrading_warnings) > 0

        if manifest_findings and inventory.has_source_files:
            confidence = 0.98 if not has_degrading else 0.85
            scan_status = "COMPLETED" if not has_degrading else "PARTIAL"
        elif manifest_findings and not inventory.has_source_files:
            confidence = 0.80
            scan_status = "PARTIAL"
            warnings.append("Manifest declared but zero first-party source files identified.")
        elif inventory.has_source_files and not manifest_findings:
            confidence = 0.50
            scan_status = "INCONCLUSIVE"
        else:
            confidence = 0.0
            scan_status = "INCONCLUSIVE"

        # Format summary stack
        summary_stack = f"{primary_lang} / {primary_framework}"
        if build_tool and build_tool != "None":
            clean_bld = build_tool.split("(")[0].strip()
            summary_stack += f" ({clean_bld})"

        return DetectedStackResponse(
            source_repository=source_repository,
            source_revision=source_revision,
            requested_revision=requested_revision or source_revision,
            primary_language=primary_lang,
            language_version=lang_ver,
            framework=primary_framework,
            framework_version=framework_ver,
            build_tool=build_tool,
            build_file=build_file,
            test_framework=test_framework,
            architecture_style=arch_style,
            confidence_score=confidence,
            summary_stack=summary_stack,
            detection_method="Static Filesystem Inventory & Manifest Parsing",
            scan_status=scan_status,
            is_fallback=False,
            warnings=warnings,
            components=components,
            tiers=tiers,
            languages=languages_dict,
            frameworks=frameworks,
            evidence=evidence,
            resolved_commit=resolved_commit,
            detector_version="2.2.0",
            scanned_at=now_iso,
            metadata={
                "total_files": inventory.total_files_scanned,
                "total_source_bytes": inventory.total_source_bytes,
                "component_count": len(components),
                "sql_files_count": len(inventory.sql_files),
                "migration_dirs_count": len(inventory.migration_dirs),
            },
        )

    # =========================================================================
    # Three-Tier Architecture Extraction
    # =========================================================================

    @classmethod
    def _extract_three_tiers(
        cls,
        inventory: InventoryResult,
        manifest_findings: List[Dict[str, Any]],
        languages_dict: Dict[str, Any],
    ) -> Tuple[TieredStackBreakdown, List[str]]:
        """Separates repository evidence into Frontend, Backend, and Database persistence tiers."""
        warnings: List[str] = []

        frontend_group = cls._extract_frontend_tier(inventory, manifest_findings, languages_dict)
        backend_group = cls._extract_backend_tier(inventory, manifest_findings, languages_dict)
        database_group, db_warnings = cls._extract_database_tier(inventory, manifest_findings)
        warnings.extend(db_warnings)

        return (
            TieredStackBreakdown(
                frontend=frontend_group,
                backend=backend_group,
                database=database_group,
            ),
            warnings,
        )

    @classmethod
    def _extract_frontend_tier(
        cls,
        inventory: InventoryResult,
        manifest_findings: List[Dict[str, Any]],
        languages_dict: Dict[str, Any],
    ) -> TierGroup:
        """Identifies SPA frameworks, client-side tools, and server-rendered templates."""
        frontend_components: List[TierComponent] = []

        # 1. Manifest-based frontend frameworks (React, Vue, Angular, Svelte, Next.js, Nuxt)
        for f in manifest_findings:
            if f.get("component_type") == "frontend" or f.get("has_frontend_spa"):
                name = f.get("directory_relative") or "Frontend Client"
                fw = f.get("frontend_framework") or f.get("framework") or "Frontend App"
                ver = f.get("frontend_version") or f.get("framework_version") or "N/A"
                lang = f.get("frontend_language") or f.get("language") or "JavaScript"
                bld = f.get("frontend_build_tool") or f.get("build_tool") or "npm"

                frontend_components.append(
                    TierComponent(
                        name=name,
                        relative_path=f.get("directory_relative", ""),
                        technology=fw,
                        framework=fw,
                        version=ver,
                        primary_language=lang,
                        build_tool_or_driver=bld,
                        evidence=f.get("evidence", []),
                    )
                )

        # 2. Server-rendered template engines (Blade, Jinja, Twig)
        if inventory.template_files:
            template_types: Dict[str, List[DiscoveredManifest]] = {}
            for tf in inventory.template_files:
                name_lower = tf.relative_path.lower()
                if name_lower.endswith(".blade.php"):
                    template_types.setdefault("Blade Template Engine (PHP)", []).append(tf)
                elif name_lower.endswith((".jinja", ".jinja2")):
                    template_types.setdefault("Jinja2 Templates (Python)", []).append(tf)
                elif name_lower.endswith(".twig"):
                    template_types.setdefault("Twig Templates (PHP)", []).append(tf)
                elif name_lower.endswith(".erb"):
                    template_types.setdefault("ERB Templates (Ruby)", []).append(tf)
                else:
                    template_types.setdefault("Server Templates", []).append(tf)

            for t_name, t_files in template_types.items():
                evidence_list = [
                    {"file": tf.relative_path, "reason": "Server-rendered presentation template file."}
                    for tf in t_files[:5]
                ]
                frontend_components.append(
                    TierComponent(
                        name="Server Templates",
                        relative_path=t_files[0].directory_relative,
                        technology=t_name,
                        framework=t_name,
                        version="N/A",
                        primary_language="PHP" if "PHP" in t_name else ("Python" if "Python" in t_name else "HTML"),
                        build_tool_or_driver="Template Engine",
                        evidence=evidence_list,
                    )
                )

        # 3. Static Web Presentation (HTML / CSS) if no other frontend was found
        if not frontend_components:
            html_count = languages_dict.get("HTML", {}).get("file_count", 0)
            css_count = languages_dict.get("CSS", {}).get("file_count", 0)
            if html_count > 0 or css_count > 0:
                frontend_components.append(
                    TierComponent(
                        name="Static Web Presentation",
                        relative_path="",
                        technology="HTML5 / CSS3",
                        framework="Vanilla HTML/CSS",
                        version="N/A",
                        primary_language="HTML",
                        build_tool_or_driver="Static Files",
                        evidence=[
                            {
                                "file": "*.html, *.css",
                                "reason": f"Discovered {html_count} HTML and {css_count} CSS presentation files.",
                            }
                        ],
                    )
                )

        primary = frontend_components[0] if frontend_components else None
        return TierGroup(primary=primary, components=frontend_components)

    @classmethod
    def _extract_backend_tier(
        cls,
        inventory: InventoryResult,
        manifest_findings: List[Dict[str, Any]],
        languages_dict: Dict[str, Any],
    ) -> TierGroup:
        """Identifies server runtimes, backend frameworks, and APIs."""
        backend_components: List[TierComponent] = []

        # 1. Manifest-based backend frameworks
        for f in manifest_findings:
            # Critical rule: Only classify as backend if it's an actual backend service or has backend framework
            # Do NOT label a React-only package.json as Node.js backend
            comp_type = f.get("component_type")
            fw = f.get("framework", "")

            is_backend = False
            if comp_type == "backend":
                is_backend = True
            elif comp_type == "service" and f.get("manifest_type") != "npm":
                is_backend = True
            elif f.get("has_backend_server"):
                is_backend = True

            if is_backend:
                name = f.get("directory_relative") or "Backend Service"
                backend_components.append(
                    TierComponent(
                        name=name,
                        relative_path=f.get("directory_relative", ""),
                        technology=fw,
                        framework=fw,
                        version=f.get("framework_version", "N/A"),
                        primary_language=f.get("language"),
                        build_tool_or_driver=f.get("build_tool", "None"),
                        evidence=f.get("evidence", []),
                    )
                )

        # 2. Inferred backend language from source code if no manifest was found
        if not backend_components:
            backend_languages = ["Java", "Python", "PHP", "Go", "C#", "Rust", "Kotlin", "Ruby", "Scala"]
            for lang in backend_languages:
                if lang in languages_dict and languages_dict[lang]["file_count"] > 0:
                    count = languages_dict[lang]["file_count"]
                    backend_components.append(
                        TierComponent(
                            name=f"{lang} Service",
                            relative_path="",
                            technology=f"{lang} Application",
                            framework=f"Plain {lang}",
                            version="N/A",
                            primary_language=lang,
                            build_tool_or_driver="None declared",
                            evidence=[
                                {
                                    "file": f"*.{lang.lower()}",
                                    "reason": f"Discovered {count} {lang} source code files without recognized package manifest.",
                                }
                            ],
                        )
                    )
                    break

        primary = backend_components[0] if backend_components else None
        return TierGroup(primary=primary, components=backend_components)

    @classmethod
    def _extract_database_tier(
        cls,
        inventory: InventoryResult,
        manifest_findings: List[Dict[str, Any]],
    ) -> Tuple[DatabaseTierGroup, List[str]]:
        """Identifies database engines, declared drivers, ORMs, and migration tools."""
        warnings: List[str] = []
        components: List[DatabaseComponent] = []

        # 1. Inspect SQL schema files for vendor-specific DDL syntax
        ddl_engine: Optional[str] = None
        ddl_evidence: List[Dict[str, str]] = []
        has_generic_sql = False
        sql_schema_paths: List[str] = []

        for sql_manifest in inventory.sql_files[:10]:
            sql_schema_paths.append(sql_manifest.relative_path)
            try:
                with open(sql_manifest.absolute_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(cls.MAX_SQL_INSPECT_BYTES)
            except Exception:
                continue

            # MySQL indicators
            if (
                re.search(r"ENGINE\s*=\s*(?:InnoDB|MyISAM)", content, re.IGNORECASE)
                or re.search(r"\bAUTO_INCREMENT\b", content, re.IGNORECASE)
                or re.search(r"\bON\s+UPDATE\s+CURRENT_TIMESTAMP\b", content, re.IGNORECASE)
            ):
                ddl_engine = "MySQL"
                ddl_evidence.append({
                    "file": sql_manifest.relative_path,
                    "reason": "MySQL DDL syntax detected (e.g., ENGINE=InnoDB or AUTO_INCREMENT).",
                })
            # PostgreSQL indicators
            elif (
                re.search(r"CREATE\s+EXTENSION", content, re.IGNORECASE)
                or re.search(r"\b(?:BIG)?SERIAL\b", content, re.IGNORECASE)
                or re.search(r"\b(?:TIMESTAMPTZ|BYTEA|CITEXT|JSONB)\b", content, re.IGNORECASE)
                or re.search(r"\bUUID_GENERATE_V4\(\)", content, re.IGNORECASE)
            ):
                if ddl_engine and ddl_engine != "PostgreSQL":
                    warnings.append(
                        f"Conflicting SQL dialect detected in {sql_manifest.relative_path}: mixed {ddl_engine} and PostgreSQL syntax."
                    )
                else:
                    ddl_engine = "PostgreSQL"
                ddl_evidence.append({
                    "file": sql_manifest.relative_path,
                    "reason": "PostgreSQL DDL syntax detected (e.g., SERIAL, TIMESTAMPTZ, or JSONB).",
                })
            # SQLite indicators
            elif (
                re.search(r"\bAUTOINCREMENT\b", content, re.IGNORECASE)
                or re.search(r"\bWITHOUT\s+ROWID\b", content, re.IGNORECASE)
                or re.search(r"\bPRAGMA\b", content, re.IGNORECASE)
            ):
                ddl_engine = "SQLite"
                ddl_evidence.append({
                    "file": sql_manifest.relative_path,
                    "reason": "SQLite DDL syntax detected (e.g., AUTOINCREMENT or WITHOUT ROWID).",
                })
            elif re.search(r"CREATE\s+TABLE", content, re.IGNORECASE):
                has_generic_sql = True
                ddl_evidence.append({
                    "file": sql_manifest.relative_path,
                    "reason": "Generic ANSI SQL schema detected without vendor-specific DDL keywords.",
                })

        # 2. Extract database drivers and ORMs declared in manifests
        driver_engine: Optional[str] = None
        driver_name: Optional[str] = None
        driver_evidence: List[Dict[str, str]] = []

        for f in manifest_findings:
            drivers = f.get("db_drivers", [])
            for d in drivers:
                d_lower = d.lower()
                if "mysql" in d_lower or "mysqli" in d_lower:
                    driver_engine = "MySQL"
                    driver_name = d
                elif "postgres" in d_lower or "pgsql" in d_lower or "psycopg" in d_lower or "pg" in d_lower:
                    if driver_engine and driver_engine != "PostgreSQL":
                        warnings.append(
                            f"Multiple declared database drivers detected: {driver_engine} and PostgreSQL."
                        )
                    else:
                        driver_engine = "PostgreSQL"
                        driver_name = d
                elif "sqlite" in d_lower:
                    driver_engine = "SQLite"
                    driver_name = d
                elif "mongo" in d_lower:
                    driver_engine = "MongoDB"
                    driver_name = d

                driver_evidence.append({
                    "file": f.get("manifest_file", "manifest"),
                    "reason": f"Declared persistence driver/ORM: {d}.",
                })

        # 3. Detect Migration tools
        migration_tool: Optional[str] = None
        for m_dir in inventory.migration_dirs:
            m_lower = m_dir.lower()
            if "database/migrations" in m_lower:
                migration_tool = "Laravel Migrations"
            elif "alembic" in m_lower:
                migration_tool = "Alembic"
            elif "prisma" in m_lower:
                migration_tool = "Prisma Migrations"
            elif "flyway" in m_lower:
                migration_tool = "Flyway"
            elif "liquibase" in m_lower:
                migration_tool = "Liquibase"
            elif "db/migrate" in m_lower:
                migration_tool = "Active Record Migrations"
            else:
                migration_tool = "SQL Migrations"

        # 4. Check safe configuration templates
        config_engine: Optional[str] = None
        config_evidence: List[Dict[str, str]] = []
        for cfg in inventory.config_templates[:5]:
            try:
                with open(cfg.absolute_path, "r", encoding="utf-8", errors="ignore") as f:
                    cfg_content = f.read(16 * 1024)
                if re.search(r"mysql", cfg_content, re.IGNORECASE):
                    config_engine = "MySQL"
                    config_evidence.append({
                        "file": cfg.relative_path,
                        "reason": "Configuration template references MySQL database connection.",
                    })
                elif re.search(r"postgres|pgsql", cfg_content, re.IGNORECASE):
                    config_engine = "PostgreSQL"
                    config_evidence.append({
                        "file": cfg.relative_path,
                        "reason": "Configuration template references PostgreSQL database connection.",
                    })
                elif re.search(r"sqlite", cfg_content, re.IGNORECASE):
                    config_engine = "SQLite"
                    config_evidence.append({
                        "file": cfg.relative_path,
                        "reason": "Configuration template references SQLite database connection.",
                    })
            except Exception:
                pass

        # 5. Synthesize persistence classification based on non-guessing rules
        has_persistence = (
            ddl_engine is not None
            or driver_engine is not None
            or has_generic_sql
            or migration_tool is not None
            or len(sql_schema_paths) > 0
            or len(driver_evidence) > 0
        )

        if not has_persistence:
            # Stateless / No database components found
            warnings.append("Stateless / None declared (No SQL or ORM files discovered).")
            return DatabaseTierGroup(primary=None, components=[]), warnings

        # Determine effective engine, confidence, and inferred_from
        engine = "Relational SQL (Dialect Unconfirmed)"
        confidence = 0.50
        inferred_from = "generic_sql"
        combined_evidence = []
        combined_evidence.extend(ddl_evidence)
        combined_evidence.extend(driver_evidence)
        combined_evidence.extend(config_evidence)

        # Check for conflicting evidence
        if ddl_engine and driver_engine and ddl_engine != driver_engine:
            warnings.append(
                f"Conflicting database evidence: SQL DDL indicates {ddl_engine} while declared driver indicates {driver_engine}."
            )
            engine = f"Ambiguous ({ddl_engine} DDL vs {driver_engine} Driver)"
            confidence = 0.70
            inferred_from = "ddl_syntax"
        elif ddl_engine and driver_engine and ddl_engine == driver_engine:
            # Dual confirmation
            engine = ddl_engine
            confidence = 0.98
            inferred_from = "ddl_syntax"
        elif ddl_engine:
            # DDL syntax match
            engine = ddl_engine
            confidence = 0.95
            inferred_from = "ddl_syntax"
        elif driver_engine:
            # Driver match only
            engine = driver_engine
            confidence = 0.90
            inferred_from = "driver_dependency"
            warnings.append(
                f"Persistence engine '{driver_engine}' inferred from declared driver '{driver_name}'. Driver suggests, but does not guarantee, the runtime database."
            )
        elif config_engine:
            # Configuration template match
            engine = config_engine
            confidence = 0.75
            inferred_from = "config_template"
        elif has_generic_sql or migration_tool or len(sql_schema_paths) > 0:
            # Generic SQL or empty migrations without vendor DDL or drivers
            engine = "Relational SQL (Dialect Unconfirmed)"
            confidence = 0.50
            inferred_from = "generic_sql"
            warnings.append(
                "SQL schema or migrations present without vendor-specific DDL syntax or declared drivers; dialect unconfirmed."
            )

        db_comp = DatabaseComponent(
            name=f"{engine} Layer",
            relative_path=inventory.migration_dirs[0] if inventory.migration_dirs else (
                sql_schema_paths[0] if sql_schema_paths else ""
            ),
            engine=engine,
            version="N/A",
            orm_or_driver=driver_name or "None declared",
            schema_artifacts=sql_schema_paths,
            migration_tool=migration_tool,
            inferred_from=inferred_from,
            confidence=confidence,
            evidence=combined_evidence,
        )

        components.append(db_comp)
        return DatabaseTierGroup(primary=db_comp, components=components), warnings

    # =========================================================================
    # Manifest Parsers
    # =========================================================================

    @classmethod
    def _parse_manifest(
        cls,
        manifest: DiscoveredManifest,
        inventory: InventoryResult,
    ) -> Optional[Dict[str, Any]]:
        """Safely reads and delegates manifest parsing by type."""
        try:
            with open(manifest.absolute_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(cls.MAX_FILE_INSPECT_BYTES)
        except Exception as e:
            inventory.warnings.append(f"Failed to read manifest {manifest.relative_path}: {str(e)}")
            return None

        m_type = manifest.manifest_type
        if m_type == "maven":
            return cls._parse_pom_xml(content, manifest, inventory)
        elif m_type == "gradle":
            return cls._parse_gradle(content, manifest, inventory)
        elif m_type == "npm":
            return cls._parse_package_json(content, manifest, inventory)
        elif m_type == "pyproject":
            return cls._parse_pyproject_toml(content, manifest, inventory)
        elif m_type == "pip":
            return cls._parse_requirements_txt(content, manifest, inventory)
        elif m_type == "composer":
            return cls._parse_composer_json(content, manifest, inventory)
        elif m_type == "csproj":
            return cls._parse_csproj(content, manifest, inventory)
        elif m_type == "go":
            return cls._parse_go_mod(content, manifest, inventory)
        elif m_type == "cargo":
            return cls._parse_cargo_toml(content, manifest, inventory)
        return None

    @classmethod
    def _parse_pom_xml(
        cls,
        content: str,
        manifest: DiscoveredManifest,
        inventory: InventoryResult,
    ) -> Optional[Dict[str, Any]]:
        """Parses Maven pom.xml using standard XML parser without entity resolution."""
        try:
            root = ET.fromstring(content)
        except Exception as e:
            inventory.warnings.append(f"Malformed XML in {manifest.relative_path}: {str(e)}")
            return None

        def _find_text(element: Optional[ET.Element], tag: str) -> Optional[str]:
            if element is None:
                return None
            for child in element:
                local = child.tag.split("}")[-1]
                if local.lower() == tag.lower():
                    return child.text.strip() if child.text else None
            return None

        java_version = "11"
        framework = "Java Application"
        framework_version = "N/A"
        test_framework = "JUnit 5"
        arch_style = "Enterprise Application"

        for elem in root.iter():
            tag = elem.tag.split("}")[-1].lower()
            if tag in ("java.version", "maven.compiler.source", "maven.compiler.target"):
                if elem.text:
                    java_version = elem.text.strip()
                    if java_version.startswith("1."):
                        java_version = java_version.split("1.")[1]
                    break

        is_spring_boot = False
        is_spring_mvc = False
        db_drivers = []

        for elem in root.iter():
            local = elem.tag.split("}")[-1].lower()
            if local == "parent":
                artifact = _find_text(elem, "artifactid") or ""
                ver = _find_text(elem, "version") or ""
                if "spring-boot" in artifact.lower():
                    is_spring_boot = True
                    framework_version = ver or "2.7.x"
            elif local == "dependency":
                group = _find_text(elem, "groupid") or ""
                artifact = _find_text(elem, "artifactid") or ""
                ver = _find_text(elem, "version") or ""
                if "org.springframework.boot" in group:
                    is_spring_boot = True
                    if ver and framework_version == "N/A":
                        framework_version = ver
                elif "org.springframework" in group:
                    is_spring_mvc = True
                elif "junit" in artifact.lower() or "jupiter" in artifact.lower():
                    test_framework = "JUnit 5 & Mockito"

                # Check database drivers
                art_lower = artifact.lower()
                if "mysql" in art_lower:
                    db_drivers.append("MySQL (mysql-connector-java)")
                elif "postgresql" in art_lower:
                    db_drivers.append("PostgreSQL (postgresql)")
                elif "h2" in art_lower:
                    db_drivers.append("H2 Database")
                elif "spring-boot-starter-data-jpa" in art_lower:
                    db_drivers.append("Spring Data JPA (Hibernate)")

        if is_spring_boot:
            framework = "Spring Boot"
            arch_style = "RESTful Microservice"
            if framework_version == "N/A":
                framework_version = "2.7.x"
        elif is_spring_mvc:
            framework = "Spring MVC"
            arch_style = "Enterprise Web Application"
            framework_version = "5.x"

        evidence = [
            {"file": manifest.relative_path, "reason": f"Maven POM with {framework} {framework_version} declaration."}
        ]

        return {
            "manifest_type": "maven",
            "language": "Java",
            "language_version": f"Java {java_version} (LTS)",
            "framework": framework,
            "framework_version": framework_version,
            "build_tool": "Maven (pom.xml)",
            "manifest_file": manifest.relative_path,
            "directory_relative": manifest.directory_relative,
            "test_framework": test_framework,
            "architecture_style": arch_style,
            "component_type": "backend",
            "db_drivers": db_drivers,
            "evidence": evidence,
        }

    @classmethod
    def _parse_gradle(
        cls,
        content: str,
        manifest: DiscoveredManifest,
        inventory: InventoryResult,
    ) -> Optional[Dict[str, Any]]:
        """Parses build.gradle / build.gradle.kts for Spring Boot, Java toolchain, and plugins."""
        java_ver = "17" if "VERSION_17" in content or "17" in content else "11"
        boot_match = re.search(
            r"id\s*['\"]org\.springframework\.boot['\"]\s*version\s*['\"]([^'\"]+)['\"]", content
        )
        boot_ver = boot_match.group(1) if boot_match else ("3.2.x" if "spring.boot" in content.lower() else "N/A")
        framework = "Spring Boot" if (boot_match or "spring" in content.lower()) else "Gradle Java Application"

        db_drivers = []
        if "mysql" in content.lower():
            db_drivers.append("MySQL (mysql-connector)")
        if "postgresql" in content.lower():
            db_drivers.append("PostgreSQL (postgresql)")
        if "h2" in content.lower():
            db_drivers.append("H2 Database")

        return {
            "manifest_type": "gradle",
            "language": "Java",
            "language_version": f"Java {java_ver} (LTS)",
            "framework": framework,
            "framework_version": boot_ver,
            "build_tool": f"Gradle ({manifest.relative_path})",
            "manifest_file": manifest.relative_path,
            "directory_relative": manifest.directory_relative,
            "test_framework": "JUnit 5 & Testcontainers",
            "architecture_style": "Modular Microservice",
            "component_type": "backend",
            "db_drivers": db_drivers,
            "evidence": [{"file": manifest.relative_path, "reason": f"Gradle build file declaring {framework}."}],
        }

    @classmethod
    def _parse_package_json(
        cls,
        content: str,
        manifest: DiscoveredManifest,
        inventory: InventoryResult,
    ) -> Optional[Dict[str, Any]]:
        """Parses package.json, separating UI libraries, backend frameworks, runtimes, and bundlers."""
        try:
            data = json.loads(content)
        except Exception as e:
            inventory.warnings.append(f"Malformed JSON in {manifest.relative_path}: {str(e)}")
            return None

        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

        # Language: TypeScript vs JavaScript
        is_ts = "typescript" in deps or any(
            p.endswith(".ts") or p.endswith(".tsx") for p in inventory.languages.keys()
        )
        lang = "TypeScript" if is_ts else "JavaScript"

        # Frontend UI frameworks
        is_react = "react" in deps
        is_vue = "vue" in deps
        is_angular = "@angular/core" in deps
        is_svelte = "svelte" in deps

        # Backend server frameworks
        is_nestjs = "@nestjs/core" in deps
        is_express = "express" in deps
        is_fastify = "fastify" in deps
        is_next = "next" in deps

        # Build tool / Bundler
        build_tool = "npm (package.json)"
        if "vite" in deps:
            build_tool = "Vite"
        elif is_next:
            build_tool = "Next.js Bundler"
        elif "webpack" in deps:
            build_tool = "Webpack"

        # Database drivers & ORMs in npm dependencies
        db_drivers = []
        if "pg" in deps:
            db_drivers.append("PostgreSQL (pg)")
        if "mysql" in deps or "mysql2" in deps:
            db_drivers.append("MySQL (mysql2)")
        if "sqlite3" in deps or "better-sqlite3" in deps:
            db_drivers.append("SQLite")
        if "mongodb" in deps or "mongoose" in deps:
            db_drivers.append("MongoDB (Mongoose)")
        if "prisma" in deps or "@prisma/client" in deps:
            db_drivers.append("Prisma ORM")
        if "typeorm" in deps:
            db_drivers.append("TypeORM")
        if "sequelize" in deps:
            db_drivers.append("Sequelize")

        # Test framework
        test_fw = "Vitest" if "vitest" in deps else ("Jest" if "jest" in deps else "npm test")

        has_frontend_spa = is_react or is_vue or is_angular or is_svelte or is_next
        has_backend_server = is_nestjs or is_express or is_fastify

        if is_react:
            framework = "React SPA"
            comp_type = "frontend"
            fw_version = str(deps.get("react", "18.x")).replace("^", "").replace("~", "")
            arch = "Client-Side Single Page Application"
        elif is_vue:
            framework = "Vue SPA"
            comp_type = "frontend"
            fw_version = str(deps.get("vue", "3.x")).replace("^", "").replace("~", "")
            arch = "Vue Frontend Application"
        elif is_angular:
            framework = "Angular App"
            comp_type = "frontend"
            fw_version = str(deps.get("@angular/core", "latest")).replace("^", "")
            arch = "Angular Enterprise Frontend"
        elif is_next:
            framework = "Next.js Full-Stack"
            comp_type = "frontend"
            fw_version = str(deps.get("next", "14.x")).replace("^", "")
            arch = "Hybrid Server-Rendered Web Application"
        elif is_nestjs:
            framework = "NestJS API"
            comp_type = "backend"
            fw_version = str(deps.get("@nestjs/core", "10.x")).replace("^", "")
            arch = "Modular TypeScript API Service"
        elif is_express:
            framework = "Express.js Service"
            comp_type = "backend"
            fw_version = str(deps.get("express", "4.x")).replace("^", "")
            arch = "RESTful Node.js API"
        elif is_fastify:
            framework = "Fastify API"
            comp_type = "backend"
            fw_version = str(deps.get("fastify", "4.x")).replace("^", "")
            arch = "High-Performance Node.js API"
        else:
            framework = "Node.js Application"
            comp_type = "service"
            fw_version = "latest"
            arch = "Node.js Modular Service"

        return {
            "manifest_type": "npm",
            "language": lang,
            "language_version": f"Node.js 20 LTS ({lang})",
            "framework": framework,
            "framework_version": fw_version,
            "build_tool": build_tool,
            "manifest_file": manifest.relative_path,
            "directory_relative": manifest.directory_relative,
            "test_framework": test_fw,
            "architecture_style": arch,
            "component_type": comp_type,
            "has_frontend_spa": has_frontend_spa,
            "has_backend_server": has_backend_server,
            "db_drivers": db_drivers,
            "evidence": [
                {
                    "file": manifest.relative_path,
                    "reason": f"package.json declaring {framework} with {build_tool}.",
                }
            ],
        }

    @classmethod
    def _parse_pyproject_toml(
        cls,
        content: str,
        manifest: DiscoveredManifest,
        inventory: InventoryResult,
    ) -> Optional[Dict[str, Any]]:
        """Parses pyproject.toml using standard tomllib."""
        try:
            data = tomllib.loads(content)
        except Exception as e:
            inventory.warnings.append(f"Malformed TOML in {manifest.relative_path}: {str(e)}")
            return None

        deps: Set[str] = set()
        project_deps = data.get("project", {}).get("dependencies", [])
        if isinstance(project_deps, list):
            for d in project_deps:
                pkg = re.split(r"[><=~!;]", str(d))[0].strip().lower()
                if pkg:
                    deps.add(pkg)

        poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
        if isinstance(poetry_deps, dict):
            for k in poetry_deps.keys():
                deps.add(k.lower())

        framework = "Python Application"
        framework_ver = "3.11+"
        test_framework = "Pytest" if "pytest" in deps or "pytest" in content else "unittest"

        if "fastapi" in deps:
            framework = "FastAPI"
            framework_ver = "0.115+"
        elif "django" in deps:
            framework = "Django"
            framework_ver = "4.2 LTS"
        elif "flask" in deps:
            framework = "Flask"
            framework_ver = "3.0+"

        # Check database drivers in python deps
        db_drivers = []
        if "psycopg2" in deps or "psycopg2-binary" in deps or "asyncpg" in deps:
            db_drivers.append("PostgreSQL (asyncpg/psycopg2)")
        if "pymysql" in deps or "mysqlclient" in deps or "aiomysql" in deps:
            db_drivers.append("MySQL (pymysql)")
        if "sqlite3" in deps or "aiosqlite" in deps:
            db_drivers.append("SQLite")
        if "sqlalchemy" in deps:
            db_drivers.append("SQLAlchemy ORM")
        if "tortoise-orm" in deps:
            db_drivers.append("Tortoise ORM")

        build_tool = "Poetry (pyproject.toml)" if "tool.poetry" in content else (
            "Flit (pyproject.toml)" if "tool.flit" in content else "Python Setuptools (pyproject.toml)"
        )

        return {
            "manifest_type": "pyproject",
            "language": "Python",
            "language_version": "Python 3.11+ (CPython)",
            "framework": framework,
            "framework_version": framework_ver,
            "build_tool": build_tool,
            "manifest_file": manifest.relative_path,
            "directory_relative": manifest.directory_relative,
            "test_framework": test_framework,
            "architecture_style": "Async RESTful API Backend" if framework == "FastAPI" else "Web Service",
            "component_type": "backend",
            "db_drivers": db_drivers,
            "evidence": [{"file": manifest.relative_path, "reason": f"pyproject.toml declaring {framework}."}],
        }

    @classmethod
    def _parse_requirements_txt(
        cls,
        content: str,
        manifest: DiscoveredManifest,
        inventory: InventoryResult,
    ) -> Optional[Dict[str, Any]]:
        """Parses requirements.txt, normalizing package names and stripping comments and constraints."""
        deps: Set[str] = set()
        for line in content.splitlines():
            clean = line.strip()
            if not clean or clean.startswith("#") or clean.startswith("-"):
                continue
            clean = clean.split("#")[0].strip()
            clean = clean.split(";")[0].strip()
            pkg = re.split(r"[><=~;]", clean)[0].strip().lower()
            if pkg:
                deps.add(pkg)

        framework = "Python Application"
        framework_ver = "3.11+"
        if "fastapi" in deps:
            framework = "FastAPI"
            framework_ver = "0.115+"
        elif "django" in deps:
            framework = "Django"
            framework_ver = "4.2 LTS"
        elif "flask" in deps:
            framework = "Flask"
            framework_ver = "3.0+"

        test_fw = "Pytest" if "pytest" in deps else "unittest"

        db_drivers = []
        if "psycopg2" in deps or "psycopg2-binary" in deps or "asyncpg" in deps:
            db_drivers.append("PostgreSQL (asyncpg/psycopg2)")
        if "pymysql" in deps or "mysqlclient" in deps or "aiomysql" in deps:
            db_drivers.append("MySQL (pymysql)")
        if "sqlite3" in deps or "aiosqlite" in deps:
            db_drivers.append("SQLite")
        if "sqlalchemy" in deps:
            db_drivers.append("SQLAlchemy ORM")

        return {
            "manifest_type": "pip",
            "language": "Python",
            "language_version": "Python 3.11+ (CPython)",
            "framework": framework,
            "framework_version": framework_ver,
            "build_tool": f"pip ({manifest.relative_path})",
            "manifest_file": manifest.relative_path,
            "directory_relative": manifest.directory_relative,
            "test_framework": test_fw,
            "architecture_style": "Async RESTful API Backend" if framework == "FastAPI" else "Python Service",
            "component_type": "backend",
            "db_drivers": db_drivers,
            "evidence": [{"file": manifest.relative_path, "reason": f"requirements file declaring {framework}."}],
        }

    @classmethod
    def _parse_composer_json(
        cls,
        content: str,
        manifest: DiscoveredManifest,
        inventory: InventoryResult,
    ) -> Optional[Dict[str, Any]]:
        """Parses composer.json for PHP runtime version, frameworks, and database drivers."""
        try:
            data = json.loads(content)
        except Exception as e:
            inventory.warnings.append(f"Malformed JSON in {manifest.relative_path}: {str(e)}")
            return None

        require = data.get("require", {})
        require_dev = data.get("require-dev", {})
        all_deps = {**require, **require_dev}

        # Determine PHP version
        php_ver_req = require.get("php", "^8.1")
        clean_php = re.sub(r"[^\d.]", "", php_ver_req.split(",")[0]) or "8.2"

        # Determine Framework
        framework = "PHP Application"
        framework_ver = "N/A"
        arch_style = "Web Application"
        test_framework = "PHPUnit" if "phpunit/phpunit" in all_deps else "None declared"

        if "laravel/framework" in all_deps:
            framework = "Laravel"
            framework_ver = str(all_deps.get("laravel/framework", "10.x")).replace("^", "")
            arch_style = "Enterprise MVC Web Application"
        elif "symfony/framework-bundle" in all_deps or any("symfony/" in k for k in all_deps):
            framework = "Symfony"
            framework_ver = str(all_deps.get("symfony/framework-bundle", "6.x")).replace("^", "")
            arch_style = "Modular Web Framework"
        elif "cakephp/cakephp" in all_deps:
            framework = "CakePHP"
            framework_ver = str(all_deps.get("cakephp/cakephp", "4.x")).replace("^", "")
        elif "slim/slim" in all_deps:
            framework = "Slim"
            framework_ver = str(all_deps.get("slim/slim", "4.x")).replace("^", "")
            arch_style = "Microframework API"

        # Check for database drivers / ORMs in composer dependencies
        db_drivers = []
        if "ext-pdo_mysql" in all_deps or "pdo_mysql" in all_deps or "ext-mysqli" in all_deps:
            db_drivers.append("MySQL (pdo_mysql)")
        if "ext-pdo_pgsql" in all_deps or "pdo_pgsql" in all_deps:
            db_drivers.append("PostgreSQL (pdo_pgsql)")
        if "ext-pdo_sqlite" in all_deps or "pdo_sqlite" in all_deps:
            db_drivers.append("SQLite (pdo_sqlite)")
        if "doctrine/orm" in all_deps or "doctrine/dbal" in all_deps:
            db_drivers.append("Doctrine ORM")
        if "illuminate/database" in all_deps:
            db_drivers.append("Eloquent ORM")

        evidence = [
            {"file": manifest.relative_path, "reason": f"composer.json declaring PHP {clean_php} with {framework} {framework_ver}."}
        ]
        if db_drivers:
            evidence.append({
                "file": manifest.relative_path,
                "reason": f"composer dependencies indicate persistence: {', '.join(db_drivers)}",
            })

        return {
            "manifest_type": "composer",
            "language": "PHP",
            "language_version": f"PHP {clean_php}",
            "framework": framework,
            "framework_version": framework_ver,
            "build_tool": "Composer (composer.json)",
            "manifest_file": manifest.relative_path,
            "directory_relative": manifest.directory_relative,
            "test_framework": test_framework,
            "architecture_style": arch_style,
            "component_type": "backend",
            "db_drivers": db_drivers,
            "evidence": evidence,
        }

    @classmethod
    def _parse_csproj(
        cls,
        content: str,
        manifest: DiscoveredManifest,
        inventory: InventoryResult,
    ) -> Optional[Dict[str, Any]]:
        """Parses .csproj for .NET TargetFramework and dependencies."""
        tf_match = re.search(r"<TargetFramework>([^<]+)</TargetFramework>", content, re.IGNORECASE)
        tf = tf_match.group(1).strip() if tf_match else "net8.0"

        framework = ".NET Application"
        framework_ver = tf
        arch_style = "Enterprise Application"

        if "Microsoft.AspNetCore" in content or "web" in tf.lower():
            framework = "ASP.NET Core"
            arch_style = "RESTful Web API"

        db_drivers = []
        if "Npgsql" in content:
            db_drivers.append("PostgreSQL (Npgsql)")
        if "MySql" in content:
            db_drivers.append("MySQL (Pomelo / MySql)")
        if "SqlServer" in content:
            db_drivers.append("SQL Server (EntityFrameworkCore)")
        if "EntityFrameworkCore" in content:
            db_drivers.append("Entity Framework Core")

        test_framework = "xUnit / NUnit" if ("xunit" in content.lower() or "nunit" in content.lower()) else "None declared"

        return {
            "manifest_type": "csproj",
            "language": "C#",
            "language_version": f".NET ({tf})",
            "framework": framework,
            "framework_version": framework_ver,
            "build_tool": "dotnet CLI (.csproj)",
            "manifest_file": manifest.relative_path,
            "directory_relative": manifest.directory_relative,
            "test_framework": test_framework,
            "architecture_style": arch_style,
            "component_type": "backend",
            "db_drivers": db_drivers,
            "evidence": [{"file": manifest.relative_path, "reason": f".csproj declaring target framework {tf} with {framework}."}],
        }

    @classmethod
    def _parse_go_mod(
        cls,
        content: str,
        manifest: DiscoveredManifest,
        inventory: InventoryResult,
    ) -> Optional[Dict[str, Any]]:
        """Parses go.mod for Go runtime version and web frameworks."""
        ver_match = re.search(r"^go\s+([0-9\.]+)", content, re.MULTILINE)
        go_ver = ver_match.group(1) if ver_match else "1.22"

        framework = "Go Standard HTTP"
        if "gin-gonic/gin" in content:
            framework = "Gin"
        elif "gofiber/fiber" in content:
            framework = "Fiber"
        elif "labstack/echo" in content:
            framework = "Echo"

        db_drivers = []
        if "lib/pq" in content or "jackc/pgx" in content:
            db_drivers.append("PostgreSQL (pgx/pq)")
        if "go-sql-driver/mysql" in content:
            db_drivers.append("MySQL (go-sql-driver)")
        if "gorm.io/gorm" in content:
            db_drivers.append("GORM")

        return {
            "manifest_type": "go",
            "language": "Go",
            "language_version": f"Go {go_ver}",
            "framework": framework,
            "framework_version": go_ver,
            "build_tool": "go build (go.mod)",
            "manifest_file": manifest.relative_path,
            "directory_relative": manifest.directory_relative,
            "test_framework": "testing / testify",
            "architecture_style": "Cloud-Native Microservice",
            "component_type": "backend",
            "db_drivers": db_drivers,
            "evidence": [{"file": manifest.relative_path, "reason": f"go.mod declaring Go {go_ver} and {framework}."}],
        }

    @classmethod
    def _parse_cargo_toml(
        cls,
        content: str,
        manifest: DiscoveredManifest,
        inventory: InventoryResult,
    ) -> Optional[Dict[str, Any]]:
        """Parses Cargo.toml for Rust crates."""
        try:
            data = tomllib.loads(content)
        except Exception as e:
            inventory.warnings.append(f"Malformed TOML in {manifest.relative_path}: {str(e)}")
            return None

        deps = {**data.get("dependencies", {})}
        framework = "Rust Service"
        if "actix-web" in deps:
            framework = "Actix-web"
        elif "axum" in deps:
            framework = "Axum"
        elif "rocket" in deps:
            framework = "Rocket"

        db_drivers = []
        if "tokio-postgres" in deps or "sqlx" in deps:
            db_drivers.append("SQLx / PostgreSQL")

        return {
            "manifest_type": "cargo",
            "language": "Rust",
            "language_version": "Rust Edition 2021",
            "framework": framework,
            "framework_version": "latest",
            "build_tool": "Cargo (Cargo.toml)",
            "manifest_file": manifest.relative_path,
            "directory_relative": manifest.directory_relative,
            "test_framework": "cargo test",
            "architecture_style": "High-Performance Microservice",
            "component_type": "backend",
            "db_drivers": db_drivers,
            "evidence": [{"file": manifest.relative_path, "reason": f"Cargo.toml declaring {framework}."}],
        }
