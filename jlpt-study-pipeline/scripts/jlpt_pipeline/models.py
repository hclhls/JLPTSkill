from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ALLOWED_JLPT_LEVELS = {"N1", "N2", "N1/N2", "unknown"}
ALLOWED_VERIFICATION_STATUSES = {"needs_review", "reviewed", "rejected"}
REQUIRED_ENTRY_FIELDS = {
    "id",
    "term",
    "kana",
    "jlpt_level_estimate",
    "category",
    "zh_tw_meaning",
    "example_ja",
    "example_zh_tw",
    "recall_prompt_zh_tw",
    "verification_status",
}


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    path: str
    message: str


@dataclass
class ValidationReport:
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add_error(self, path: str, message: str) -> None:
        self.errors.append(ValidationIssue("error", path, message))

    def add_warning(self, path: str, message: str) -> None:
        self.warnings.append(ValidationIssue("warning", path, message))


def active_entries(source: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        entry
        for entry in source.get("entries", [])
        if entry.get("verification_status") != "rejected"
    ]
