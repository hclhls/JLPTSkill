from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    ALLOWED_JLPT_LEVELS,
    ALLOWED_VERIFICATION_STATUSES,
    REQUIRED_ENTRY_FIELDS,
    ValidationReport,
)

GENERIC_RECALL_PROMPTS = {"這是什麼？", "這是什麼?", "請回答"}
REQUIRED_METADATA_STRING_FIELDS = {"topic", "language", "verification_policy"}
REQUIRED_METADATA_LIST_FIELDS = {"target_levels"}
REQUIRED_ENTRY_STRING_FIELDS = REQUIRED_ENTRY_FIELDS - {"id"}


def load_source(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source_file:
        source = json.load(source_file)
    if not isinstance(source, dict):
        raise ValueError("source JSON root must be an object")
    return source


def validate_source(source: dict[str, Any]) -> ValidationReport:
    report = ValidationReport()
    entries = source.get("entries")

    if not isinstance(entries, list):
        report.add_error("entries", "entries must be a non-empty list")
        return report
    if not entries:
        report.add_error("entries", "entries must be a non-empty list")
        return report

    _validate_metadata(source, report)

    seen_ids: dict[str, int] = {}
    for index, entry in enumerate(entries):
        entry_path = f"entries[{index}]"
        if not isinstance(entry, dict):
            report.add_error(entry_path, "entry must be an object")
            continue

        for field in sorted(REQUIRED_ENTRY_FIELDS):
            value = entry.get(field)
            if value is None or value == "":
                report.add_error(f"{entry_path}.{field}", f"Missing required field: {field}")

        for field in sorted(REQUIRED_ENTRY_STRING_FIELDS):
            value = entry.get(field)
            if value not in (None, "") and not isinstance(value, str):
                report.add_error(f"{entry_path}.{field}", f"{field} must be a string")

        similar_terms = entry.get("similar_terms")
        if similar_terms not in (None, "") and (
            not isinstance(similar_terms, list)
            or any(not isinstance(term, str) for term in similar_terms)
        ):
            report.add_error(
                f"{entry_path}.similar_terms",
                "similar_terms must be a list of strings",
            )

        entry_id = entry.get("id")
        if entry_id not in (None, ""):
            if not isinstance(entry_id, str):
                report.add_error(f"{entry_path}.id", "id must be a non-empty string")
            elif entry_id in seen_ids:
                report.add_error(f"{entry_path}.id", f"Duplicate id: {entry_id}")
            else:
                seen_ids[entry_id] = index

        jlpt_level = entry.get("jlpt_level_estimate")
        if jlpt_level not in (None, "") and jlpt_level not in ALLOWED_JLPT_LEVELS:
            report.add_error(
                f"{entry_path}.jlpt_level_estimate",
                f"Invalid jlpt_level_estimate: {jlpt_level}",
            )

        verification_status = entry.get("verification_status")
        if (
            verification_status not in (None, "")
            and verification_status not in ALLOWED_VERIFICATION_STATUSES
        ):
            report.add_error(
                f"{entry_path}.verification_status",
                f"Invalid verification_status: {verification_status}",
            )

        if verification_status == "needs_review":
            report.add_warning(
                f"{entry_path}.verification_status",
                "verification_status is needs_review",
            )

        recall_prompt = entry.get("recall_prompt_zh_tw")
        if isinstance(recall_prompt, str) and (
            len(recall_prompt) < 8 or recall_prompt in GENERIC_RECALL_PROMPTS
        ):
            report.add_warning(
                f"{entry_path}.recall_prompt_zh_tw",
                "recall_prompt_zh_tw may be too generic",
            )

        example_ja = entry.get("example_ja")
        if isinstance(example_ja, str) and (len(example_ja) < 8 or len(example_ja) > 120):
            report.add_warning(
                f"{entry_path}.example_ja",
                "example_ja length may be outside the useful range",
            )

    return report


def _validate_metadata(source: dict[str, Any], report: ValidationReport) -> None:
    metadata = source.get("metadata")
    if not isinstance(metadata, dict):
        report.add_error("metadata", "metadata must be an object")
        return

    for field in sorted(REQUIRED_METADATA_STRING_FIELDS):
        value = metadata.get(field)
        if value in (None, ""):
            report.add_error(
                f"metadata.{field}",
                f"Missing required metadata field: {field}",
            )
        elif not isinstance(value, str):
            report.add_error(f"metadata.{field}", f"{field} must be a string")

    target_levels = metadata.get("target_levels")
    if target_levels in (None, ""):
        report.add_error(
            "metadata.target_levels",
            "Missing required metadata field: target_levels",
        )
    elif not isinstance(target_levels, list) or any(
        not isinstance(level, str) for level in target_levels
    ):
        report.add_error(
            "metadata.target_levels",
            "target_levels must be a list of strings",
        )


def render_validation_report(report: ValidationReport) -> str:
    lines = ["# Validation Report", "", f"Status: {'PASS' if report.ok else 'FAIL'}", ""]
    lines.extend(_render_section("Errors", report.errors))
    lines.append("")
    lines.extend(_render_section("Warnings", report.warnings))
    return "\n".join(lines)


def _render_section(title: str, issues: list[Any]) -> list[str]:
    lines = [f"## {title}"]
    if not issues:
        lines.append("None")
        return lines
    for issue in issues:
        lines.append(f"- `{issue.path}`: {issue.message}")
    return lines
