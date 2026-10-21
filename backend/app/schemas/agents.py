"""Specialist agent and execution run schemas."""

from typing import Optional
from pydantic import BaseModel, Field


class AgentRunResponse(BaseModel):
    run_id: str = Field(..., description="Unique execution run identifier.")
    job_id: str = Field(..., description="Associated job ID.")
    agent_name: str = Field(..., description="Name of the specialist agent (e.g. CodeWriter, Verifier).")
    status: str = Field(..., description="Active, Idle, Completed, or Failed.")
    role_description: str = Field(..., description="Specialist responsibility in the pipeline.")
    tooling: str = Field(..., description="Whitelisted tooling available to this agent.")
    input_tokens: int = Field(0, description="Tokens consumed during the run.")
    output_tokens: int = Field(0, description="Tokens emitted by model completions.")
    cost_usd: float = Field(0.0, description="Cost calculated from model token usage.")
    started_at: str
    completed_at: Optional[str] = None


class AgentRunDetailResponse(AgentRunResponse):
    model: str = Field(..., description="Model identifier used for inference.")
    prompt_version: str = Field(..., description="Version of the agent prompt template.")
    execution_trace: list[str] = Field(default_factory=list, description="Ordered timeline of inner-loop tool actions.")


class AgentRunListResponse(BaseModel):
    items: list[AgentRunResponse]
    total: int
