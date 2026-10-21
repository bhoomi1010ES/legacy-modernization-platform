"""Role domain model for Role-Based Access Control (RBAC)."""

from typing import List
from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Role(Base):
    __tablename__ = "roles"

    role_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    permissions: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    memberships = relationship("JobMembership", back_populates="role")
