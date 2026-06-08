import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "source.sample.json"
sys.path.insert(0, str(ROOT / "scripts"))

import jlpt_pipeline.video as video
from jlpt_pipeline.validation import load_source
from jlpt_pipeline.video import (
    build_video_assets,
    escape_ass,
    ffmpeg_available,
    ffmpeg_filter_path,
    write_narration,
    write_silent_video,
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


def test_escape_ass_neutralizes_control_sequences_and_braces():
    escaped = escape_ass("A\\N B\\h {x}\nC")

    assert escaped == "A＼N B＼h (x)\\NC"
    assert r"\h" not in escaped
    assert escaped.count(r"\N") == 1
    assert "{" not in escaped
    assert "}" not in escaped


def test_ffmpeg_filter_path_escapes_filter_special_characters():
    path = Path("/tmp/a,b:c[d]e'f\\g/subtitles.ass")

    assert (
        ffmpeg_filter_path(path)
        == "ass=filename='/tmp/a\\,b\\:c\\[d\\]e\\'f\\\\g/subtitles.ass'"
    )


def test_write_silent_video_uses_escaped_ass_filter(tmp_path, monkeypatch):
    source = load_source(SAMPLE)
    out_dir = tmp_path / "a,b:c[d]e'f\\g"
    calls = []

    def capture_run(command, **kwargs):
        calls.append((command, kwargs))

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(video.subprocess, "run", capture_run)

    output = write_silent_video(source, out_dir)

    assert output == out_dir / "video.mp4"
    command, kwargs = calls[0]
    vf_arg = command[command.index("-vf") + 1]
    assert vf_arg == ffmpeg_filter_path(out_dir / "subtitles.ass")
    assert kwargs["check"] is True


def test_build_video_assets_without_ffmpeg_still_writes_text_assets(tmp_path, monkeypatch):
    source = load_source(SAMPLE)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    assets = build_video_assets(source, tmp_path, make_video=True)

    assert assets["narration"].exists()
    assert assets["subtitles"].exists()
    assert assets["video"] is None
    assert not ffmpeg_available()
