"""Contracts for universal test inventory discovery."""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DiscoveredTestRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    test_id: str = Field(..., description="Unique test identifier")
    file_path: str = Field(..., description="Relative file path")
    test_framework: str = Field(..., description="Detected framework or test runner")
    test_cases_count: int = Field(default=1, ge=0)
    test_names: List[str] = Field(default_factory=list)
    location_line: Optional[int] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class TestInventory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_test_files: int = Field(default=0, ge=0)
    total_test_cases: int = Field(default=0, ge=0)
    discovered_tests: List[DiscoveredTestRecord] = Field(default_factory=list)
    frameworks_detected: List[str] = Field(default_factory=list)
    source_paths: List[str] = Field(default_factory=list)


TestInventory.__test__ = False

