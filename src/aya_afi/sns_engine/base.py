"""Shared types for the SNS engine (content generation + validation).

Kept framework-agnostic so validators / post-processors / generators can all
depend on these without pulling in IPC or LLM concerns.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1


class SnsKind(StrEnum):
    threads = "threads"
    bluesky = "bluesky"
    note = "note"


class PostMode(StrEnum):
    preparation = "preparation"
    affiliate = "affiliate"


class ValidationSeverity(StrEnum):
    error = "error"  # Must fix before posting.
    warning = "warning"  # Advisory; posting is allowed.
    info = "info"  # Neutral observation (e.g. char count).


IssueField = Literal["body", "title", "tags", "reply_body"]


class ValidationIssue(BaseModel):
    """One lint finding against a generated post."""

    model_config = ConfigDict(extra="forbid")

    severity: ValidationSeverity
    rule_id: str = Field(..., description="Stable identifier, e.g. 'threads.too_many_hashtags'")
    message: str = Field(..., description="User-facing message in Japanese")
    field: IssueField | None = None


class ValidationReport(BaseModel):
    """Aggregated validation result for one post."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION, ge=1)
    sns: SnsKind
    mode: PostMode
    char_count: int = Field(ge=0)
    issues: list[ValidationIssue] = Field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == ValidationSeverity.error for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.error)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.warning)
