"""Authentication and user schemas."""

from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., description="User's work email address.")
    password: str = Field(..., min_length=8, description="User password (minimum 8 characters).")


class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="User's work email address.")
    full_name: str = Field(..., min_length=2, max_length=255, description="Full name or display name.")
    password: str = Field(..., min_length=8, max_length=128, description="User password (minimum 8 characters).")
    role: Optional[str] = Field("DEVELOPER", description="Requested workspace role (e.g. DEVELOPER, REVIEWER, ADMIN).")


class UserResponse(BaseModel):
    user_id: str = Field(..., description="Unique UUIDv7 user identifier.")
    email: str = Field(..., description="User's primary work email.")
    full_name: str = Field(..., description="Display name of the user.")
    role: str = Field(..., description="Global workspace role (e.g. ADMIN, REVIEWER, DEVELOPER).")
    status: str = Field("ACTIVE", description="Account status.")
    permissions: list[str] = Field(default_factory=list, description="Effective role permissions.")
    created_at: str = Field(..., description="ISO 8601 creation timestamp.")


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=8)
    new_password: str = Field(..., min_length=8)
