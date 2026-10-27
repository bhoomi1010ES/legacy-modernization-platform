"""Typed, audited and permission-aware registry for agent tools."""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol

from app.schemas.agent_runtime import AgentContext, AgentTask, ToolCall, ToolCategory, ToolResult, ToolSpec
from app.services.secret_redactor import SecretRedactor, get_secret_redactor


class ToolRegistryError(RuntimeError):
    pass


class ToolNotFoundError(ToolRegistryError):
    pass


class ToolPermissionError(ToolRegistryError):
    pass


class ToolSchemaError(ToolRegistryError):
    pass


class ToolExecutionError(ToolRegistryError):
    pass


ToolHandler = Callable[[Dict[str, Any], AgentContext], Any | Awaitable[Any]]
AuditHook = Callable[[Dict[str, Any]], Any | Awaitable[Any]]


@dataclass(frozen=True)
class RegisteredTool:
    spec: ToolSpec
    handler: ToolHandler


def validate_json_schema(value: Any, schema: Dict[str, Any], path: str = "$") -> None:
    """Validate the safe JSON-schema subset used by tool and output contracts."""
    if not schema:
        return
    if "oneOf" in schema:
        successes = 0
        for candidate in schema["oneOf"]:
            try:
                validate_json_schema(value, candidate, path)
                successes += 1
            except ToolSchemaError:
                pass
        if successes != 1:
            raise ToolSchemaError(f"{path} must match exactly one schema")
        return
    expected = schema.get("type")
    types = {
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "null": type(None),
    }
    if expected in types and (isinstance(value, bool) and expected in {"integer", "number"} or not isinstance(value, types[expected])):
        raise ToolSchemaError(f"{path} must be of type {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise ToolSchemaError(f"{path} must be one of {schema['enum']}")
    if expected == "object":
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise ToolSchemaError(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = set(value) - set(properties)
            if extras:
                raise ToolSchemaError(f"{path} contains unsupported properties: {sorted(extras)}")
        for key, item in value.items():
            if key in properties:
                validate_json_schema(item, properties[key], f"{path}.{key}")
    elif expected == "array":
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ToolSchemaError(f"{path} exceeds maxItems")
        for index, item in enumerate(value):
            validate_json_schema(item, schema.get("items", {}), f"{path}[{index}]")
    elif expected == "string":
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ToolSchemaError(f"{path} exceeds maxLength")


class ToolRegistry:
    def __init__(self, *, redactor: Optional[SecretRedactor] = None, audit_hook: Optional[AuditHook] = None) -> None:
        self._tools: Dict[str, RegisteredTool] = {}
        self.redactor = redactor or get_secret_redactor()
        self.audit_hook = audit_hook

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool '{spec.name}' is already registered")
        self._tools[spec.name] = RegisteredTool(spec=spec, handler=handler)

    def get_spec(self, name: str) -> ToolSpec:
        try:
            return self._tools[name].spec
        except KeyError as exc:
            raise ToolNotFoundError(f"Unknown tool '{name}'") from exc

    def specs_for(self, allowed_tools: list[str]) -> list[ToolSpec]:
        return [self.get_spec(name) for name in allowed_tools]

    async def _audit(self, payload: Dict[str, Any]) -> None:
        if not self.audit_hook:
            return
        result = self.audit_hook(self.redactor.redact_object(payload))
        if inspect.isawaitable(result):
            await result

    async def execute(self, call: ToolCall, *, task: AgentTask, context: AgentContext, max_output_bytes: int) -> ToolResult:
        started = perf_counter()
        try:
            registered = self._tools.get(call.tool_name)
            if registered is None:
                raise ToolNotFoundError(f"Unknown tool '{call.tool_name}'")
            spec = registered.spec
            if call.tool_name not in task.allowed_tools:
                raise ToolPermissionError(f"Agent '{task.agent_name}' is not allowed to call '{call.tool_name}'")
            if spec.required_permission and spec.required_permission not in context.permissions:
                raise ToolPermissionError(f"Tool '{call.tool_name}' requires permission '{spec.required_permission}'")
            validate_json_schema(call.arguments, spec.parameters_schema)
            await self._audit({"event": "TOOL_CALL", "run_id": context.run_id, "call": call.model_dump(mode="json")})
            output = registered.handler(call.arguments, context)
            if inspect.isawaitable(output):
                output = await asyncio.wait_for(output, timeout=spec.timeout_seconds)
            encoded = json.dumps(output, default=str).encode("utf-8")
            truncated = len(encoded) > max_output_bytes
            if truncated:
                output = encoded[:max_output_bytes].decode("utf-8", errors="replace") + "...[TRUNCATED]"
            result = ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                ok=True,
                output=self.redactor.redact_object(output),
                duration_ms=(perf_counter() - started) * 1000,
                truncated=truncated,
            )
        except (ToolRegistryError, asyncio.TimeoutError) as exc:
            result = ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                ok=False,
                error=self.redactor.redact_text(str(exc)),
                duration_ms=(perf_counter() - started) * 1000,
            )
        except Exception as exc:
            result = ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                ok=False,
                error=f"Tool execution failed: {type(exc).__name__}",
                duration_ms=(perf_counter() - started) * 1000,
            )
        await self._audit({"event": "TOOL_RESULT", "run_id": context.run_id, "result": result.model_dump(mode="json")})
        return result


def _resolve_workspace_path(workspace: Path, relative_path: str) -> Path:
    candidate = (workspace / relative_path).resolve()
    root = workspace.resolve()
    if candidate != root and root not in candidate.parents:
        raise ToolPermissionError("Path escapes the authorized workspace")
    return candidate


def build_read_only_repository_registry(workspace: Path, **kwargs: Any) -> ToolRegistry:
    """Build the baseline registry. Mutating and process tools are intentionally not enabled here."""
    registry = ToolRegistry(**kwargs)

    def repository_list(args: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        target = _resolve_workspace_path(workspace, args.get("path", "."))
        if not target.is_dir():
            raise ToolExecutionError("Requested repository path is not a directory")
        files = [str(item.relative_to(workspace)).replace("\\", "/") for item in target.rglob("*") if item.is_file()]
        return {"files": sorted(files)[:500], "truncated": len(files) > 500}

    def file_read(args: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        target = _resolve_workspace_path(workspace, args["path"])
        max_bytes = min(int(args.get("max_bytes", 131072)), 1_048_576)
        if not target.is_file():
            raise ToolExecutionError("Requested file does not exist")
        raw = target.read_bytes()[: max_bytes + 1]
        return {"path": args["path"], "content": raw[:max_bytes].decode("utf-8", errors="replace"), "truncated": len(raw) > max_bytes}

    registry.register(ToolSpec(
        name="repository_list", description="List files below the scoped repository root.",
        category=ToolCategory.READ_ONLY, is_read_only=True,
        parameters_schema={"type": "object", "properties": {"path": {"type": "string", "maxLength": 512}}, "additionalProperties": False},
        required_permission="repository:read",
    ), repository_list)
    registry.register(ToolSpec(
        name="file_read", description="Read a UTF-8 file below the scoped repository root.",
        category=ToolCategory.READ_ONLY, is_read_only=True,
        parameters_schema={"type": "object", "properties": {"path": {"type": "string", "maxLength": 512}, "max_bytes": {"type": "integer"}}, "required": ["path"], "additionalProperties": False},
        required_permission="repository:read",
    ), file_read)
    return registry


class SandboxExecutor(Protocol):
    """Capability boundary supplied only by the platform's isolated sandbox layer."""
    async def edit_file(self, relative_path: str, content: str) -> Any: ...
    async def run_tests(self, command: list[str]) -> Any: ...
    async def git_commit(self, message: str) -> Any: ...


def register_write_execute_tools(registry: ToolRegistry, sandbox: SandboxExecutor) -> None:
    """Opt in mutating tools only when a policy-enforcing sandbox implementation is supplied."""
    registry.register(ToolSpec(
        name="sandbox_edit", description="Edit a file through the isolated workspace sandbox.",
        category=ToolCategory.WRITE_EXECUTE, is_read_only=False,
        parameters_schema={"type": "object", "properties": {"path": {"type": "string", "maxLength": 512}, "content": {"type": "string"}}, "required": ["path", "content"], "additionalProperties": False},
        required_permission="repository:write",
    ), lambda args, context: sandbox.edit_file(args["path"], args["content"]))
    registry.register(ToolSpec(
        name="test_runner", description="Run an approved test command in the isolated sandbox.",
        category=ToolCategory.WRITE_EXECUTE, is_read_only=False,
        parameters_schema={"type": "object", "properties": {"command": {"type": "array", "items": {"type": "string"}, "maxItems": 32}}, "required": ["command"], "additionalProperties": False},
        required_permission="sandbox:execute", timeout_seconds=300,
    ), lambda args, context: sandbox.run_tests(args["command"]))
    registry.register(ToolSpec(
        name="git_commit", description="Commit staged sandbox changes after policy checks.",
        category=ToolCategory.WRITE_EXECUTE, is_read_only=False,
        parameters_schema={"type": "object", "properties": {"message": {"type": "string", "maxLength": 200}}, "required": ["message"], "additionalProperties": False},
        required_permission="repository:commit",
    ), lambda args, context: sandbox.git_commit(args["message"]))
