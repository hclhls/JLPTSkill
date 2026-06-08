import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "source.sample.json"
sys.path.insert(0, str(ROOT / "scripts"))

from jlpt_pipeline.validation import load_source, render_validation_report, validate_source


def _sample_source():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def test_sample_source_is_valid():
    source = load_source(SAMPLE)

    report = validate_source(source)

    assert report.ok
    assert report.errors == []


def test_missing_required_field_is_error():
    source = _sample_source()
    del source["entries"][0]["term"]

    report = validate_source(source)

    assert not report.ok
    assert report.errors[0].path == "entries[0].term"
    assert "Missing required field" in report.errors[0].message


def test_duplicate_id_is_error():
    source = _sample_source()
    source["entries"][1]["id"] = source["entries"][0]["id"]

    report = validate_source(source)

    assert any("Duplicate id" in error.message for error in report.errors)


def test_malformed_id_type_is_error_not_crash():
    source = load_source(SAMPLE)
    source["entries"][0]["id"] = []

    report = validate_source(source)

    assert not report.ok
    assert any(
        issue.path == "entries[0].id" and "id must be a non-empty string" in issue.message
        for issue in report.errors
    )


def test_invalid_enum_values_are_errors():
    source = _sample_source()
    source["entries"][0]["jlpt_level_estimate"] = "N3"
    source["entries"][1]["verification_status"] = "maybe"

    report = validate_source(source)
    messages = [error.message for error in report.errors]

    assert "Invalid jlpt_level_estimate: N3" in messages
    assert "Invalid verification_status: maybe" in messages


def test_empty_entries_is_error():
    source = {"metadata": {}, "entries": []}

    report = validate_source(source)

    assert not report.ok
    assert report.errors[0].path == "entries"


def test_quality_warnings_are_rendered():
    source = _sample_source()
    source["entries"][0]["recall_prompt_zh_tw"] = "這是什麼？"

    report = validate_source(source)
    rendered = render_validation_report(report)

    assert "# Validation Report" in rendered
    assert "recall_prompt_zh_tw may be too generic" in rendered
    assert "needs_review" in rendered


def test_required_scalar_fields_must_be_strings():
    source = _sample_source()
    source["entries"][0]["term"] = ["しみじみ"]
    source["entries"][0]["example_ja"] = {"text": "卒業式で先生の言葉を思い出した。"}

    report = validate_source(source)

    assert not report.ok
    assert any(
        issue.path == "entries[0].term" and "term must be a string" in issue.message
        for issue in report.errors
    )
    assert any(
        issue.path == "entries[0].example_ja" and "example_ja must be a string" in issue.message
        for issue in report.errors
    )


def test_metadata_required_fields_are_validated():
    source = _sample_source()
    source["metadata"] = {"topic": ["JLPT"], "target_levels": "N1", "language": "", "verification_policy": "ai_generated_requires_review"}

    report = validate_source(source)

    assert not report.ok
    assert any(
        issue.path == "metadata.topic" and "topic must be a string" in issue.message
        for issue in report.errors
    )
    assert any(
        issue.path == "metadata.target_levels" and "target_levels must be a list of strings" in issue.message
        for issue in report.errors
    )
    assert any(
        issue.path == "metadata.language" and "Missing required metadata field" in issue.message
        for issue in report.errors
    )
