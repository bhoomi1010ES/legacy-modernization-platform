"""Deterministic Scenario Discovery and Characterization Test Generation Layer.

Derives candidate behavioral scenarios from:
1. Existing test files and test methods (fixture/input/assertion extraction).
2. Public interfaces, routes, controllers, and service methods.
3. Persistence entities and SQL operations.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field

from app.schemas.phase4 import LegacyModel, PublicInterface, RepositoryInventory
from app.schemas.phase5 import NormalizationRule, Scenario

logger = logging.getLogger(__name__)


class ScenarioProvenance(BaseModel):
    generation_type: str
    generator_version: str
    source_location: str
    source_hash: str


class ScenarioCandidate(BaseModel):
    scenario_id: str = Field(default_factory=lambda: f"scen_{uuid.uuid4().hex[:10]}")
    name: str
    description: str
    module: str
    interface: str
    behavior: str
    source_file: str
    source_symbol: Optional[str] = None
    source_location: Optional[str] = None
    source_hash: Optional[str] = None
    entrypoint: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)
    expected_outputs: Optional[Any] = None
    expected_side_effects: Optional[Any] = None
    confidence: float = 1.0
    evidence_refs: List[str] = Field(default_factory=list)
    status: str = "DISCOVERED"  # DISCOVERED, REVIEW_REQUIRED, APPROVED, REJECTED, EXECUTABLE
    generation_type: str = "EXISTING_TEST"  # EXISTING_TEST, GENERATED_CHARACTERIZATION, INTERFACE_CONTRACT
    generator_version: Optional[str] = None
    expected_behavior_source: Optional[str] = None

    @property
    def provenance(self) -> ScenarioProvenance:
        return ScenarioProvenance(
            generation_type=self.generation_type,
            generator_version=self.generator_version or "v5.0-auto",
            source_location=self.source_location or f"{self.source_file}#{self.source_symbol or self.name}",
            source_hash=self.source_hash or "sha256:discovered_source_hash",
        )


class ScenarioDiscoveryService:
    """Discovers existing tests and generates missing characterization scenarios."""

    def discover_scenarios(
        self,
        workspace_path: Optional[Path],
        legacy_model: Optional[LegacyModel] = None,
        inventory: Optional[RepositoryInventory] = None,
    ) -> List[ScenarioCandidate]:
        """Derive candidate behavioral scenarios from repository and legacy model evidence."""
        candidates: List[ScenarioCandidate] = []
        covered_interfaces: set[str] = set()

        # 1. Discover from existing test files in the workspace
        if workspace_path and workspace_path.exists():
            candidates.extend(self._discover_from_workspace_tests(workspace_path, covered_interfaces))

        # 2. If inventory has test files not reached directly, discover them
        if inventory and workspace_path and workspace_path.exists():
            for f in inventory.files:
                if f.is_test and (workspace_path / f.path).exists():
                    p = workspace_path / f.path
                    if p.is_file() and p.suffix == ".py":
                        test_cands = self._parse_python_test_file(p, workspace_path, covered_interfaces)
                        existing_ids = {c.name for c in candidates}
                        for tc in test_cands:
                            if tc.name not in existing_ids:
                                candidates.append(tc)

        # 3. Generate missing characterization tests for public interfaces without adequate test coverage
        if legacy_model and legacy_model.public_interfaces:
            for iface in legacy_model.public_interfaces:
                if iface.name not in covered_interfaces:
                    gen_cand = self._generate_interface_characterization_scenario(iface, legacy_model)
                    candidates.append(gen_cand)
                    covered_interfaces.add(iface.name)

        # 4. Generate missing characterization tests for uncovered workspace source entrypoints
        if workspace_path and workspace_path.exists():
            for py_file in workspace_path.glob("**/*.py"):
                rel_str = str(py_file.relative_to(workspace_path)).replace("\\", "/")
                if "test" in rel_str.lower() or "venv" in rel_str.lower() or ".git" in rel_str:
                    continue
                source_cands = self._parse_source_file_for_entrypoints(py_file, workspace_path, covered_interfaces)
                existing_names = {c.name for c in candidates}
                for sc in source_cands:
                    if sc.name not in existing_names:
                        candidates.append(sc)

        # 5. If legacy model has modules but no candidates were found, generate root characterization vectors
        if not candidates and legacy_model and legacy_model.modules:
            for mod in legacy_model.modules:
                candidates.append(
                    ScenarioCandidate(
                        name=f"char_{mod.module_id}_baseline",
                        description=f"Generated characterization vector for module {mod.module_id}",
                        module=mod.module_id,
                        interface=mod.entry_points[0] if mod.entry_points else "main",
                        behavior=f"Capture execution output for {mod.responsibility}",
                        source_file=mod.path,
                        source_symbol=mod.entry_points[0] if mod.entry_points else None,
                        inputs={"module": mod.module_id, "action": "execute"},
                        expected_outputs=None,
                        confidence=0.85,
                        evidence_refs=[f"module:{mod.module_id}"],
                        status="EXECUTABLE",
                        generation_type="GENERATED_CHARACTERIZATION",
                        generator_version="v4.5-auto-char",
                        expected_behavior_source="legacy_model_module_discovery",
                    )
                )

        logger.info(
            "Discovered %d scenario candidates (executable=%d, review_required=%d)",
            len(candidates),
            sum(1 for c in candidates if c.status in ("EXECUTABLE", "APPROVED")),
            sum(1 for c in candidates if c.status == "REVIEW_REQUIRED"),
        )
        return candidates

    def _discover_from_workspace_tests(
        self,
        workspace_path: Path,
        covered_interfaces: set[str],
    ) -> List[ScenarioCandidate]:
        candidates: List[ScenarioCandidate] = []
        test_patterns = ["**/test_*.py", "**/*_test.py", "**/tests/*.py"]
        visited_paths: set[Path] = set()

        for pattern in test_patterns:
            for file_path in workspace_path.glob(pattern):
                if file_path.is_file() and file_path not in visited_paths:
                    visited_paths.add(file_path)
                    if file_path.suffix == ".py":
                        candidates.extend(self._parse_python_test_file(file_path, workspace_path, covered_interfaces))
                    else:
                        candidates.extend(self._parse_generic_test_file(file_path, workspace_path, covered_interfaces))

        return candidates

    def _parse_python_test_file(
        self,
        file_path: Path,
        workspace_path: Path,
        covered_interfaces: set[str],
    ) -> List[ScenarioCandidate]:
        candidates: List[ScenarioCandidate] = []
        try:
            rel_path = str(file_path.relative_to(workspace_path)).replace("\\", "/")
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(file_path))

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith("test_") or node.name.endswith("_test"):
                        cand = self._extract_scenario_from_ast_func(node, rel_path)
                        candidates.append(cand)
                        covered_interfaces.add(cand.interface)
        except Exception as exc:
            logger.debug("Failed to parse test file %s: %s", file_path, exc)

        return candidates

    def _extract_scenario_from_ast_func(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        rel_path: str,
    ) -> ScenarioCandidate:
        func_name = func_node.name
        docstring = ast.get_docstring(func_node) or f"Test {func_name}"

        # Analyze assertions to determine if expected output is known
        has_assertions = False
        extracted_expected: Any = None
        is_safe_assert = False

        for subnode in ast.walk(func_node):
            if isinstance(subnode, ast.Assert):
                has_assertions = True
                # Check for comparison: assert x == y
                if isinstance(subnode.test, ast.Compare):
                    if any(isinstance(op, ast.Eq) for op in subnode.test.ops):
                        comparator = subnode.test.comparators[0]
                        if isinstance(comparator, ast.Constant):
                            extracted_expected = comparator.value
                            is_safe_assert = True
                        elif isinstance(comparator, (ast.Dict, ast.List)):
                            try:
                                extracted_expected = ast.literal_eval(comparator)
                                is_safe_assert = True
                            except Exception:
                                pass

        # Derive module from path
        parts = rel_path.split("/")
        mod_name = parts[1] if len(parts) > 1 and parts[0] in ("tests", "src") else (parts[0] if parts else "root")
        if mod_name.endswith(".py"):
            mod_name = mod_name.replace(".py", "").replace("test_", "")

        clean_interface = func_name.replace("test_", "")
        status = "EXECUTABLE" if is_safe_assert or not has_assertions else "REVIEW_REQUIRED"

        return ScenarioCandidate(
            name=func_name,
            description=docstring.strip().split("\n")[0],
            module=mod_name or "domain",
            interface=clean_interface,
            behavior=docstring.strip().split("\n")[0] or f"Executes {func_name}",
            source_file=rel_path,
            source_symbol=func_name,
            inputs={"test_target": func_name, "scope": "unit"},
            expected_outputs=extracted_expected,
            confidence=0.95 if is_safe_assert else 0.75,
            evidence_refs=[f"test_file:{rel_path}", f"test_symbol:{func_name}"],
            status=status,
            generation_type="EXISTING_TEST",
            generator_version="v4.5-test-extractor",
            expected_behavior_source="test_assertions" if is_safe_assert else "test_execution",
        )

    def _parse_generic_test_file(
        self,
        file_path: Path,
        workspace_path: Path,
        covered_interfaces: set[str],
    ) -> List[ScenarioCandidate]:
        rel_path = str(file_path.relative_to(workspace_path)).replace("\\", "/")
        stem = file_path.stem
        covered_interfaces.add(stem)
        return [
            ScenarioCandidate(
                name=f"test_{stem}",
                description=f"Generic test suite extracted from {rel_path}",
                module="tests",
                interface=stem,
                behavior=f"Runs test suite in {rel_path}",
                source_file=rel_path,
                source_symbol=None,
                inputs={"file": rel_path},
                expected_outputs=None,
                confidence=0.7,
                evidence_refs=[f"test_file:{rel_path}"],
                status="REVIEW_REQUIRED",
                generation_type="EXISTING_TEST",
                generator_version="v4.5-generic",
                expected_behavior_source="file_manifest",
            )
        ]

    def _generate_interface_characterization_scenario(
        self,
        iface: PublicInterface,
        legacy_model: LegacyModel,
    ) -> ScenarioCandidate:
        """Generates missing characterization test for uncovered public interface."""
        clean_name = re.sub(r"[^A-Za-z0-9_]", "_", iface.name).strip("_")
        mod_name = iface.consumer_modules[0] if iface.consumer_modules else "api"

        return ScenarioCandidate(
            name=f"char_{clean_name}",
            description=f"Generated characterization vector for public interface {iface.name}",
            module=mod_name,
            interface=iface.name,
            behavior=f"Capture golden baseline for {iface.interface_type} interface {iface.name}",
            source_file=iface.location_path,
            source_symbol=iface.name,
            entrypoint=iface.signature,
            inputs={"interface": iface.name, "type": iface.interface_type},
            expected_outputs=None,  # Represents behavior to capture, not fabricated output
            confidence=0.9,
            evidence_refs=list(iface.evidence_refs) + [f"interface:{iface.interface_id}"],
            status="EXECUTABLE",
            generation_type="GENERATED_CHARACTERIZATION",
            generator_version="v5.0-auto",
            expected_behavior_source="legacy_ast_public_interface",
        )

    def _parse_source_file_for_entrypoints(
        self,
        file_path: Path,
        workspace_path: Path,
        covered_interfaces: set[str],
    ) -> List[ScenarioCandidate]:
        candidates: List[ScenarioCandidate] = []
        rel_path = str(file_path.relative_to(workspace_path)).replace("\\", "/")
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        mod_name = file_path.parent.name
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                cls_name = node.name
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                        clean_name = f"{cls_name}_{item.name}"
                        if item.name not in covered_interfaces and clean_name not in covered_interfaces:
                            covered_interfaces.add(item.name)
                            candidates.append(
                                ScenarioCandidate(
                                    name=f"char_{clean_name}",
                                    description=f"Generated characterization vector for method {cls_name}.{item.name}",
                                    module=mod_name,
                                    interface=item.name,
                                    behavior=f"Capture execution output for {cls_name}.{item.name}",
                                    source_file=rel_path,
                                    source_symbol=f"{cls_name}.{item.name}",
                                    entrypoint=item.name,
                                    inputs={"target": f"{cls_name}.{item.name}", "class": cls_name, "method": item.name},
                                    expected_outputs=None,
                                    confidence=0.85,
                                    evidence_refs=[f"source_file:{rel_path}", f"source_symbol:{cls_name}.{item.name}"],
                                    status="EXECUTABLE",
                                    generation_type="GENERATED_CHARACTERIZATION",
                                    generator_version="v5.0-auto",
                                    expected_behavior_source="ast_source_entrypoint",
                                )
                            )
            elif isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                func_name = node.name
                if func_name not in covered_interfaces:
                    covered_interfaces.add(func_name)
                    candidates.append(
                        ScenarioCandidate(
                            name=f"char_{func_name}",
                            description=f"Generated characterization vector for function {func_name}",
                            module=mod_name,
                            interface=func_name,
                            behavior=f"Capture execution output for {func_name}",
                            source_file=rel_path,
                            source_symbol=func_name,
                            entrypoint=func_name,
                            inputs={"target": func_name},
                            expected_outputs=None,
                            confidence=0.85,
                            evidence_refs=[f"source_file:{rel_path}", f"source_symbol:{func_name}"],
                            status="EXECUTABLE",
                            generation_type="GENERATED_CHARACTERIZATION",
                            generator_version="v5.0-auto",
                            expected_behavior_source="ast_source_entrypoint",
                        )
                    )
        return candidates

    def to_executable_scenarios(self, candidates: List[ScenarioCandidate]) -> List[Scenario]:
        """Converts approved or executable candidate scenarios into executable Phase 5 Scenario objects."""
        scenarios: List[Scenario] = []
        for cand in candidates:
            if cand.status in ("EXECUTABLE", "APPROVED"):
                scen_dict = {
                    "name": cand.name,
                    "module": cand.module,
                    "interface": cand.interface,
                    "behavior": cand.behavior,
                    "inputs": cand.inputs,
                    "normalization": [],
                }
                if cand.expected_outputs is not None:
                    scen_dict["expected"] = cand.expected_outputs
                scenarios.append(Scenario(**scen_dict))
        return scenarios

    export_executable_scenarios = to_executable_scenarios


scenario_discovery_service = ScenarioDiscoveryService()
