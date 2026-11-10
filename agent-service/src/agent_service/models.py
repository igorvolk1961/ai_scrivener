from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LlmOptions(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = Field(min_length=1, max_length=100)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2000, ge=1, le=100000)


class StepRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    protocol_version: int = 1
    run_version: int
    task: dict[str, Any]
    agent: dict[str, Any]
    context: dict[str, Any] = Field(default_factory=dict)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    llm: LlmOptions
    allowed_tools: list[str] = Field(default_factory=list)
    policy: dict[str, Any] = Field(default_factory=dict)
