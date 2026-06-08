import sys
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "source.sample.json"
sys.path.insert(0, str(ROOT / "scripts"))

from jlpt_pipeline import cli
from jlpt_pipeline.cli import main


def test_validate_command_writes_report(tmp_path):
    result = main(["validate", "--source", str(SAMPLE), "--out", str(tmp_path)])

    assert result == 0
    report = tmp_path / "validation_report.md"
    assert report.exists()
    assert "Status: PASS" in report.read_text(encoding="utf-8")


def test_validate_invalid_json_returns_1_and_writes_source_load_error(tmp_path):
    source = tmp_path / "invalid.json"
    source.write_text("{not valid json", encoding="utf-8")

    result = main(["validate", "--source", str(source), "--out", str(tmp_path)])

    assert result == 1
    report = tmp_path / "validation_report.md"
    assert report.exists()
    report_text = report.read_text(encoding="utf-8")
    assert "Status: FAIL" in report_text
    assert "Source load error" in report_text


def test_dry_run_command_writes_character_estimate(tmp_path):
    result = main(["dry-run", "--source", str(SAMPLE), "--out", str(tmp_path)])

    assert result == 0
    report = tmp_path / "validation_report.md"
    assert "Estimated TTS characters" in report.read_text(encoding="utf-8")


def test_dry_run_command_writes_validation_report_for_invalid_source(tmp_path):
    source = tmp_path / "invalid.json"
    source.write_text(
        json.dumps({"entries": [{"id": "missing-term"}]}),
        encoding="utf-8",
    )

    result = main(["dry-run", "--source", str(source), "--out", str(tmp_path)])

    assert result == 1
    report = tmp_path / "validation_report.md"
    assert report.exists()
    assert "Missing required field" in report.read_text(encoding="utf-8")


def test_build_command_writes_core_outputs_without_tts(tmp_path):
    result = main(
        [
            "build",
            "--source",
            str(SAMPLE),
            "--out",
            str(tmp_path),
            "--deck-name",
            "Sample JLPT",
            "--tts-provider",
            "none",
            "--slug",
            "sample",
        ]
    )

    assert result == 0
    assert (tmp_path / "sample.md").exists()
    assert (tmp_path / "sample-jlpt.apkg").exists()
    assert (tmp_path / "anki.csv").exists()
    assert (tmp_path / "narration.txt").exists()
    assert (tmp_path / "subtitles.ass").exists()
    assert (tmp_path / "validation_report.md").exists()


def test_build_with_azure_missing_credentials_warns_and_returns_0(tmp_path, monkeypatch):
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)

    result = main(
        [
            "build",
            "--source",
            str(SAMPLE),
            "--out",
            str(tmp_path),
            "--deck-name",
            "Sample JLPT",
            "--tts-provider",
            "azure",
            "--slug",
            "sample",
        ]
    )

    assert result == 0
    report_text = (tmp_path / "validation_report.md").read_text(encoding="utf-8")
    assert "TTS status: WARN" in report_text
    assert "AZURE_SPEECH_KEY and AZURE_SPEECH_REGION" in report_text


def test_build_video_asset_failure_is_reported_and_returns_0(tmp_path, monkeypatch):
    def fail_video_assets(source, out_dir, make_video=False):
        raise RuntimeError("ffmpeg failed")

    monkeypatch.setattr(cli, "build_video_assets", fail_video_assets)

    result = main(
        [
            "build",
            "--source",
            str(SAMPLE),
            "--out",
            str(tmp_path),
            "--deck-name",
            "Sample JLPT",
            "--tts-provider",
            "none",
            "--slug",
            "sample",
            "--video",
        ]
    )

    assert result == 0
    report_text = (tmp_path / "validation_report.md").read_text(encoding="utf-8")
    assert "ffmpeg failed" in report_text
