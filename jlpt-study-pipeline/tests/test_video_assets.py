import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "source.sample.json"
sys.path.insert(0, str(ROOT / "scripts"))

from jlpt_pipeline.validation import load_source
from jlpt_pipeline.video import (
    build_video_assets,
    ffmpeg_available,
    write_narration,
    write_subtitles,
)


def test_write_narration_skips_rejected_entries(tmp_path):
    source = load_source(SAMPLE)

    output = write_narration(source, tmp_path)
    text = output.read_text(encoding="utf-8")

    assert "しみじみ" in text
    assert "ぐずぐず" in text
    assert "ざあざあ" not in text


def test_write_subtitles_contains_ass_headers(tmp_path):
    source = load_source(SAMPLE)

    output = write_subtitles(source, tmp_path)
    text = output.read_text(encoding="utf-8")

    assert "[Script Info]" in text
    assert "[Events]" in text
    assert "しみじみ" in text


def test_build_video_assets_without_ffmpeg_still_writes_text_assets(tmp_path, monkeypatch):
    source = load_source(SAMPLE)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    assets = build_video_assets(source, tmp_path, make_video=True)

    assert assets["narration"].exists()
    assert assets["subtitles"].exists()
    assert assets["video"] is None
    assert not ffmpeg_available()
