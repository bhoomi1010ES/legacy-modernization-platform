"""Module Planner: Formulates detailed, verifiable implementation tasks for a single module."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from app.schemas.phase4 import (
    LegacyModel,
    ModulePlanningUnit,
    PlanningTask,
    TargetBlueprint,
    TargetComponent,
)

logger = logging.getLogger(__name__)


class ModulePlanner:
    """Specialist Planner generating granular implementation tasks and acceptance criteria for a module."""

    def __init__(
        self,
        module_id: Optional[str] = None,
        component: Optional[TargetComponent] = None,
        context: Optional[Any] = None,
    ):
        self.module_id = module_id or (component.component_id if component else None)
        self.component = component
        self.context = context

    def plan_module(
        self,
        blueprint: TargetBlueprint,
        legacy_model: Optional[LegacyModel] = None,
        component: Optional[TargetComponent] = None,
        legacy_module: Optional[Any] = None,
        context: Optional[Any] = None,
        g1_decisions: Optional[List[Any]] = None,
        characterization_suite: Optional[Dict[str, Any]] = None,
        schema_data_plan: Optional[Dict[str, Any]] = None,
    ) -> Optional[ModulePlanningUnit]:
        """Formulates implementation tasks, test harnesses, and acceptance criteria for this module.
        
        Consumes G1 decisions, characterization evidence, and schema constraints to adapt plan.
        """
        try:
            comp = component or self.component
            if comp is None:
                mod_name = getattr(legacy_module, "path", "shared").replace("/", ".").strip(".")
                comp = TargetComponent(
                    component_id=self.module_id or getattr(legacy_module, "module_id", f"comp_{uuid.uuid4().hex[:8]}"),
                    name=mod_name or "CoreComponent",
                    target_path=f"src/{mod_name}",
                    responsibilities=[getattr(legacy_module, "responsibility", "Core business functionality")],
                    mapped_legacy_modules=[getattr(legacy_module, "module_id", "mod_1")],
                    interfaces=[],
                    dependencies=[],
                )

            effective_module_id = comp.component_id or self.module_id or "mod_core"

            # 1. Evaluate G1 Decisions for this component
            ctx = context or getattr(self, "context", None)
            active_g1 = g1_decisions or (getattr(ctx, "g1_decisions", []) if ctx else [])
            active_char = characterization_suite or (getattr(ctx, "characterization_suite", None) if ctx else None)
            active_schema = schema_data_plan or (getattr(ctx, "schema_data_plan", None) if ctx else None)

            is_descoped = False
            is_wrap_service = False
            is_accept_substitute = False
            is_rewrite_custom = False
            g1_reason = ""

            comp_name_lower = (comp.name or "").lower()
            effective_mod_lower = effective_module_id.lower()

            for decision_item in active_g1:
                cap_id = str(getattr(decision_item, "capability_id", "")).lower()
                dec_type = getattr(decision_item, "decision", "")
                dec_val = getattr(dec_type, "value", str(dec_type)).upper()
                reason = getattr(decision_item, "reason", "")

                matches = (
                    cap_id in comp_name_lower
                    or cap_id in effective_mod_lower
                    or any(cap_id in str(m).lower() for m in comp.mapped_legacy_modules)
                    or (comp_name_lower and comp_name_lower in cap_id)
                )
                if matches:
                    g1_reason = reason
                    reason_upper = reason.upper()
                    if "DESCOPE" in dec_val or "DESCOPE" in reason_upper:
                        is_descoped = True
                        break
                    elif "WRAP" in dec_val or "WRAP" in reason_upper:
                        is_wrap_service = True
                    elif "SUBSTITUTE" in dec_val or "SUBSTITUTE" in reason_upper:
                        is_accept_substitute = True
                    elif "REWRITE" in dec_val or "CUSTOM" in dec_val or "CUSTOM" in reason_upper or "REWRITE" in reason_upper:
                        is_rewrite_custom = True

            # If G1 decision descoped this capability, remove it from the conversion plan!
            if is_descoped:
                logger.info("Module %s descoped by human G1 decision: %s", effective_module_id, g1_reason)
                return None

            tasks: List[PlanningTask] = []

            # Task 1: Module Structure & Contract Definition (evidence-driven, technology-agnostic)
            task1_id = f"task_{effective_module_id}_scaffold"
            resp_summary = ", ".join(comp.responsibilities[:2]) if comp.responsibilities else comp.name
            tasks.append(PlanningTask(
                task_id=task1_id,
                module_id=effective_module_id,
                title=f"Scaffold structure and contracts for {comp.name}",
                description=f"Create target component location {comp.target_path} and declare interfaces/types for {resp_summary}.",
                dependencies=[],
                interfaces=comp.interfaces,
                migration_steps=[
                    f"Establish target directory/structure at {comp.target_path}",
                    f"Declare module contracts, interfaces, and specifications based on observed legacy capabilities",
                ],
                required_tests=["Contract syntax and type checking"],
                acceptance_criteria=[
                    f"Target path {comp.target_path} exists with valid structure declaration",
                    "Module contract declarations parse and typecheck with zero errors",
                ],
                estimate_hours=1.5,
                risk="LOW",
                required_tools=["linter", "type_checker"],
                environment_requirements=["Target runtime environment"],
            ))

            # Task 2: Core Capability Implementation (adapted dynamically by G1 decisions, characterization, schema)
            task2_id = f"task_{effective_module_id}_service"
            task2_deps = [task1_id]

            if is_wrap_service:
                task2_title = f"Implement wrapper facade adapter for {comp.name}"
                task2_desc = f"Encapsulate legacy {comp.name} behind modern facade per G1 WRAP_SERVICE decision: {g1_reason}"
                task2_risk = "LOW"
                task2_est = 1.5
                task2_ac = [
                    f"Legacy capability '{comp.name}' wrapped in modern facade without logic rewrite",
                    "Wrapper facade conforms to G1 service wrapping strategy",
                ]
            elif is_rewrite_custom:
                task2_title = f"Custom build implementation from scratch for {comp.name}"
                task2_desc = f"Implement custom target logic per G1 REWRITE_CUSTOM decision: {g1_reason}"
                task2_risk = "HIGH"
                task2_est = 5.0
                task2_ac = [
                    "Custom implementation verified against legacy behavioral contract",
                    "Zero functional regressions against characterization baseline",
                ]
            else:
                task2_title = f"Implement core logic and capabilities for {comp.name}"
                task2_desc = f"Implement {comp.name} preserving legacy business behavior and capabilities: {resp_summary}."
                task2_risk = "MEDIUM"
                task2_est = 3.0
                task2_ac = [
                    f"Component methods and logic return expected output matching legacy behavior",
                    f"Fulfills declared responsibilities: {resp_summary}",
                ]

            if is_accept_substitute:
                task2_ac.append(f"Modernized substitute library adopted conforming to G1 approval: {g1_reason}")

            # Incorporate Characterization Evidence into Task 2
            matching_char_cases = []
            if active_char and isinstance(active_char, dict):
                cases = active_char.get("cases", [])
                for c in cases:
                    c_mod = str(c.get("module", "")).lower()
                    c_iface = str(c.get("interface", "")).lower()
                    c_name = str(c.get("name", "")).lower()
                    if (
                        c_mod == effective_mod_lower
                        or c_mod in comp_name_lower
                        or comp_name_lower in c_mod
                        or any(c_iface == str(i).lower() for i in comp.interfaces)
                        or comp_name_lower in c_name
                    ):
                        matching_char_cases.append(c)

            for case in matching_char_cases[:3]:
                case_name = case.get("name", "vector")
                case_id = case.get("test_case_id", "")
                task2_ac.append(
                    f"Behavioral equivalence: Characterization vector '{case_name}' (ID: {case_id[:8] if case_id else 'n/a'}) passes with golden output"
                )

            # Incorporate Schema/Data Constraints into Task 2
            if active_schema and isinstance(active_schema, dict):
                tables = active_schema.get("tables", [])
                if tables:
                    task2_ac.append(
                        f"Data persistence conforms to target SchemaMigrationPlan v1 ({len(tables)} tables analyzed)"
                    )
                    task2_deps.append("task_db_migration_001")

            tasks.append(PlanningTask(
                task_id=task2_id,
                module_id=effective_module_id,
                title=task2_title,
                description=task2_desc,
                dependencies=task2_deps,
                interfaces=comp.interfaces,
                migration_steps=[
                    f"Implement core component logic for {comp.name} fulfilling declared responsibilities",
                    "Wire required dependency contracts and internal state management",
                ],
                required_tests=["Unit test suite", "Behavioral equivalence tests"],
                acceptance_criteria=task2_ac,
                estimate_hours=task2_est,
                risk=task2_risk,
                required_tools=["compiler", "test_runner"],
                environment_requirements=["Target runtime environment"],
            ))

            # Task 3: Public Interface Adapter OR Integration Verification (dynamically driven by observed interfaces)
            task3_id = f"task_{effective_module_id}_controller"
            if comp.interfaces:
                tasks.append(PlanningTask(
                    task_id=task3_id,
                    module_id=effective_module_id,
                    title=f"Wire public interface adapters for {comp.name}",
                    description=f"Expose public endpoints and interfaces conforming to preserved legacy contracts: {', '.join(comp.interfaces[:4])}.",
                    dependencies=[task2_id],
                    interfaces=comp.interfaces,
                    migration_steps=[
                        "Implement interface routes, adapters, or handlers matching legacy signatures",
                        "Bind request/parameter validation and response serializers",
                    ],
                    required_tests=["Interface endpoint tests", "Characterization replay tests"],
                    acceptance_criteria=[
                        "Public interfaces handle valid inputs with matching response structure",
                        "Input validation handles malformed or edge-case parameters gracefully",
                    ],
                    estimate_hours=2.5,
                    risk="MEDIUM",
                    required_tools=["test_runner"],
                    environment_requirements=["Target runtime environment"],
                ))
            else:
                tasks.append(PlanningTask(
                    task_id=task3_id,
                    module_id=effective_module_id,
                    title=f"Verify module integration and regression suite for {comp.name}",
                    description=f"Verify end-to-end integration and ensure zero regressions for {comp.name}.",
                    dependencies=[task2_id],
                    interfaces=[],
                    migration_steps=[
                        f"Execute integration tests connecting {comp.name} to target dependencies",
                        "Verify zero functional regressions against legacy baseline",
                    ],
                    required_tests=["Module integration test suite", "Regression verification"],
                    acceptance_criteria=[
                        f"All integration assertions for {comp.name} pass cleanly",
                        "Component integrates seamlessly with target application dependencies",
                    ],
                    estimate_hours=1.5,
                    risk="LOW",
                    required_tools=["test_runner"],
                    environment_requirements=["Target runtime environment"],
                ))

            total_hours = sum(t.estimate_hours for t in tasks)
            evidence_refs: List[str] = []
            if legacy_model and hasattr(legacy_model, "evidence_index") and legacy_model.evidence_index:
                evidence_refs = list(legacy_model.evidence_index.keys())[:10]

            module_deps = list(comp.dependencies)
            if active_schema and isinstance(active_schema, dict) and active_schema.get("tables"):
                if "mod_db_migration" not in module_deps:
                    module_deps.append("mod_db_migration")

            planning_unit = ModulePlanningUnit(
                module_id=effective_module_id,
                responsibility=comp.responsibilities[0] if comp.responsibilities else f"Core module {comp.name}",
                source_scope=[next((m.path for m in legacy_model.modules if m.module_id == identifier), identifier) if legacy_model else identifier for identifier in comp.mapped_legacy_modules],
                target_scope=[comp.target_path],
                dependencies=module_deps,
                interfaces=comp.interfaces,
                migration_steps=[
                    f"1. Scaffold {comp.name} contracts",
                    f"2. Implement domain services",
                    f"3. Expose controllers and adapters",
                ],
                implementation_tasks=tasks,
                required_tests=[f"test_harness_{effective_module_id}"],
                acceptance_criteria=[ac for t in tasks for ac in t.acceptance_criteria],
                risk=task2_risk,
                estimate_hours=total_hours,
                evidence_refs=evidence_refs,
            )
            return planning_unit
        except Exception as exc:
            logger.exception("plan_module failed | module_id=%s | %s: %s", self.module_id, type(exc).__name__, exc)
            raise
