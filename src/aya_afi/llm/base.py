"""LLM provider Protocol + pydantic data classes.

Concrete providers (``gemini``, ``claude``, ``mock``, ``ollama``) implement
``LLMProvider``. Callers should only depend on this module.

See: docs/decisions/004-llm-provider-abstraction.md.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1


class GenerationRequest(BaseModel):
    """Input to an LLM. Prompt composition is the caller's responsibility."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION, ge=1)
    system_prompt: str
    user_prompt: str
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=1024, gt=0, le=8192)
    stop_sequences: list[str] = Field(default_factory=list)
    # When "json", providers pass response_mime_type hints to the backend.
    # The caller is still responsible for parsing the result.
    response_format: Literal["text", "json"] = "text"


class GenerationResponse(BaseModel):
    """Output from an LLM. ``provider`` and ``model`` are recorded for audit."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION, ge=1)
    text: str
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    model: str
    provider: str
    duration_ms: int = Field(ge=0)


@runtime_checkable
class LLMProvider(Protocol):
    """All concrete providers must satisfy this shape."""

    name: str

    async def generate(self, req: GenerationRequest) -> GenerationResponse: ...

    async def health_check(self) -> bool: ...
