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
