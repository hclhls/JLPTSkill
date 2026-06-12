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


def test_write_narration_skips_rejected_entries_and_anki_prompts(tmp_path):
    source = load_source(SAMPLE)

    output = write_narration(source, tmp_path)
    text = output.read_text(encoding="utf-8")

    assert "しみじみ" in text
    assert "ぐずぐず" in text
    assert "ざあざあ" not in text
    assert "Recall prompt" not in text
    assert "Answer:" not in text


def test_write_subtitles_contains_ass_headers_without_anki_prompts(tmp_path):
    source = load_source(SAMPLE)

    output = write_subtitles(source, tmp_path)
    text = output.read_text(encoding="utf-8")

    assert "[Script Info]" in text
    assert "[Events]" in text
    assert "Style: Term,Noto Sans CJK JP,128," in text
    assert "Style: Body,Noto Sans CJK JP,62," in text
    assert "しみじみ" in text
    assert "表示深切感受" not in text
    assert "Answer" not in text


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


def test_subtitle_lines_use_actual_audio_durations_without_overlap(tmp_path, monkeypatch):
    source = load_source(SAMPLE)
    audio_paths = [tmp_path / "audio" / f"clip-{index}.mp3" for index in range(10)]
    audio_paths[0].parent.mkdir()
    for audio_path in audio_paths:
        audio_path.write_bytes(b"audio")
    durations = {audio_path: 1.0 + index for index, audio_path in enumerate(audio_paths)}

    monkeypatch.setattr(video, "audio_duration_seconds", lambda path: durations[path])

    lines = video.subtitle_lines(source, audio_paths=audio_paths)

    assert [line["text"] for line in lines[:5]] == [
        "しみじみ (しみじみ)",
        "しみじみ (しみじみ)",
        "深切地、由衷地；靜靜感受某種情緒",
        "卒業式で先生の言葉をしみじみと思い出した。",
        "在畢業典禮上，我深深想起老師說過的話。",
    ]
    assert [round(line["start"], 1) for line in lines[:10]] == [
        0.0,
        1.6,
        4.2,
        7.8,
        12.4,
        18.0,
        24.6,
        32.2,
        40.8,
        50.4,
    ]
    assert all(current["end"] <= next_line["start"] for current, next_line in zip(lines, lines[1:]))


def test_write_video_with_audio_places_mp3_inputs_on_duration_driven_timeline(tmp_path, monkeypatch):
    source = load_source(SAMPLE)
    audio_paths = [tmp_path / "audio" / f"clip-{index}.mp3" for index in range(10)]
    audio_paths[0].parent.mkdir()
    for audio_path in audio_paths:
        audio_path.write_bytes(b"audio")
    durations = {audio_path: 1.0 + index for index, audio_path in enumerate(audio_paths)}
    calls = []

    def capture_run(command, **kwargs):
        calls.append((command, kwargs))

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(video, "audio_duration_seconds", lambda path: durations[path])
    monkeypatch.setattr(video.subprocess, "run", capture_run)

    output = video.write_video(source, tmp_path, audio_paths=audio_paths)

    assert output == tmp_path / "video.mp4"
    command, kwargs = calls[0]
    filter_complex = command[command.index("-filter_complex") + 1]
    assert "concat=" not in filter_complex
    assert "[1:a]adelay=0|0[a1]" in filter_complex
    assert "[2:a]adelay=1600|1600[a2]" in filter_complex
    assert "[3:a]adelay=4200|4200[a3]" in filter_complex
    assert "[8:a]adelay=32200|32200[a8]" in filter_complex
    assert "[9:a]adelay=40800|40800[a9]" in filter_complex
    assert "[10:a]adelay=50400|50400[a10]" in filter_complex
    assert command[command.index("-i") + 1].endswith("d=61.0")
    assert command[command.index("-map") + 1] == "0:v"
    assert command[command.index("-map", command.index("-map") + 1) + 1] == "[aout]"
    assert kwargs["check"] is True


def test_build_video_assets_without_ffmpeg_still_writes_text_assets(tmp_path, monkeypatch):
    source = load_source(SAMPLE)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    assets = build_video_assets(source, tmp_path, make_video=True)

    assert assets["narration"].exists()
    assert assets["subtitles"].exists()
    assert assets["video"] is None
    assert not ffmpeg_available()
