"""Standardized error envelope and platform exceptions."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    field: Optional[str] = Field(None, description="Request field that caused the error, if applicable.")
    issue: str = Field(..., description="Explanation of the specific validation or business constraint issue.")


class ErrorPayload(BaseModel):
    code: str = Field(..., description="Machine-readable uppercase error code.")
    message: str = Field(..., description="Human-readable descriptive error message.")
    request_id: str = Field(..., description="Unique request tracing correlation identifier.")
    details: Optional[list[ErrorDetail]] = Field(None, description="Optional array of field-level errors.")


class ErrorEnvelope(BaseModel):
    error: ErrorPayload


class PlatformException(Exception):
    """Base class for all application-level errors."""
    def __init__(self, code: str, message: str, status_code: int = 400, details: Optional[list[ErrorDetail]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class IllegalStateTransitionException(PlatformException):
    def __init__(self, current_state: str, target_state: str, reason: str = ""):
        msg = f"Cannot transition job from '{current_state}' to '{target_state}'."
        if reason:
            msg += f" {reason}"
        super().__init__(
            code="ILLEGAL_STATE_TRANSITION",
            message=msg,
            status_code=409,
            details=[ErrorDetail(field="status", issue=reason or "Preconditions for target state not satisfied.")],
        )


class GatePolicyException(PlatformException):
    def __init__(self, message: str, issue: str = ""):
        super().__init__(
            code="GATE_POLICY_VIOLATION",
            message=message,
            status_code=422,
            details=[ErrorDetail(field="rationale", issue=issue or message)],
        )


class UnauthorizedException(PlatformException):
    def __init__(self, message: str = "Authentication required to access this resource."):
        super().__init__(code="UNAUTHORIZED", message=message, status_code=401)


class ForbiddenException(PlatformException):
    def __init__(
        self,
        message: str = "You do not have permission to perform this action.",
        details: Optional[list] = None,
    ):
        super().__init__(code="FORBIDDEN", message=message, status_code=403, details=details)


class NotFoundException(PlatformException):
    def __init__(
        self,
        resource: str = "Resource",
        resource_id: str = "",
        entity_name: Optional[str] = None,
        entity_id: Optional[str] = None,
    ):
        res = entity_name or resource
        rid = entity_id or resource_id
        super().__init__(
            code="NOT_FOUND",
            message=f"{res} with ID '{rid}' was not found.",
            status_code=404,
        )


class ConflictException(PlatformException):
    def __init__(self, message: str, details: Optional[list] = None):
        super().__init__(code="CONFLICT", message=message, status_code=409, details=details)


class ValidationException(PlatformException):
    def __init__(self, message: str, details: Optional[list] = None):
        super().__init__(code="VALIDATION_ERROR", message=message, status_code=422, details=details)


# ---------------------------------------------------------------------------
# Workspace Lifecycle & Repository Staging Exceptions
# ---------------------------------------------------------------------------
class WorkspaceException(ConflictException):
    """Base exception for all repository workspace lifecycle failures."""
    def __init__(self, code: str, message: str, details: Optional[list] = None):
        super().__init__(message=message, details=details)
        self.code = code


class WorkspaceNotFoundException(WorkspaceException):
    def __init__(self, message: str = "Staged Git repository workspace not found."):
        super().__init__(code="WORKSPACE_NOT_FOUND", message=message)


class WorkspaceInvalidException(WorkspaceException):
    def __init__(self, message: str = "Repository workspace is inaccessible or invalid."):
        super().__init__(code="WORKSPACE_INVALID", message=message)


class WorkspaceCorruptedException(WorkspaceException):
    def __init__(self, message: str = "Repository workspace is corrupted or missing required files."):
        super().__init__(code="WORKSPACE_CORRUPTED", message=message)


class WorkspaceWrongRepositoryException(WorkspaceException):
    def __init__(self, message: str = "Repository workspace belongs to another job or unexpected source."):
        super().__init__(code="WORKSPACE_WRONG_REPOSITORY", message=message)


class WorkspaceGitInvalidException(WorkspaceException):
    def __init__(self, message: str = "Repository workspace Git state is invalid or missing HEAD."):
        super().__init__(code="WORKSPACE_GIT_INVALID", message=message)


class WorkspaceRecoveryFailedException(WorkspaceException):
    def __init__(self, message: str = "Failed to recover repository workspace from authoritative source."):
        super().__init__(code="WORKSPACE_RECOVERY_FAILED", message=message)


class IncompleteModelOutputError(ValidationException):
    """Raised when model provider output was truncated (e.g. hit max_tokens / finish_reason: length)."""
    def __init__(self, message: str = "Model generation truncated: output exceeded token limit."):
        super().__init__(message=message)
        self.code = "INCOMPLETE_MODEL_OUTPUT"


class MalformedModelOutputError(ValidationException):
    """Raised when model provider output cannot be parsed into the expected JSON structure."""
    def __init__(self, message: str = "Model generation returned malformed or invalid JSON."):
        super().__init__(message=message)
        self.code = "MALFORMED_MODEL_OUTPUT"

