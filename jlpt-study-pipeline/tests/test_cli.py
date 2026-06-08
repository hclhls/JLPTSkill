import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "source.sample.json"
sys.path.insert(0, str(ROOT / "scripts"))

from jlpt_pipeline.cli import main


def test_validate_command_writes_report(tmp_path):
    result = main(["validate", "--source", str(SAMPLE), "--out", str(tmp_path)])

    assert result == 0
    report = tmp_path / "validation_report.md"
    assert report.exists()
    assert "Status: PASS" in report.read_text(encoding="utf-8")


def test_dry_run_command_writes_character_estimate(tmp_path):
    result = main(["dry-run", "--source", str(SAMPLE), "--out", str(tmp_path)])

    assert result == 0
    report = tmp_path / "validation_report.md"
    assert "Estimated TTS characters" in report.read_text(encoding="utf-8")


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
