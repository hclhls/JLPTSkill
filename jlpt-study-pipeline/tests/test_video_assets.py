import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "source.sample.json"
sys.path.insert(0, str(ROOT / "scripts"))

import jlpt_pipeline.video as video
from jlpt_pipeline.models import VideoFieldConfig
from jlpt_pipeline.validation import load_source
from jlpt_pipeline.video import (
    build_video_assets,
    escape_ass,
    ffmpeg_available,
    ffmpeg_filter_path,
    write_narration,
    write_short_videos,
    write_silent_video,
    write_subtitles,
    write_video,
    write_video_file,
)
from jlpt_pipeline.models import EXAMPLE_STYLE_SENTENCE


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
    # Body font size bumped to 76
    assert "Style: Body,Noto Sans CJK JP,76," in text
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


def test_ffmpeg_filter_path_includes_escaped_fontsdir_when_provided():
    path = Path("/tmp/a,b/subtitles.ass")
    fonts_dir = Path("/tmp/fonts:cjk")

    assert (
        ffmpeg_filter_path(path, fonts_dir=fonts_dir)
        == "ass=filename='/tmp/a\\,b/subtitles.ass':fontsdir='/tmp/fonts\\:cjk'"
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
    assert vf_arg == ffmpeg_filter_path(
        out_dir / "subtitles.ass", fonts_dir=video.bundled_fonts_dir()
    )
    assert kwargs["check"] is True


def test_subtitle_lines_use_actual_audio_durations_without_overlap(tmp_path, monkeypatch):
    source = load_source(SAMPLE)
    # New pipeline: 4 audio clips per entry (term1, term2, zh_tw_meaning, example_ja)
    audio_paths = [tmp_path / "audio" / f"clip-{index}.mp3" for index in range(8)]
    audio_paths[0].parent.mkdir()
    for audio_path in audio_paths:
        audio_path.write_bytes(b"audio")
    durations = {audio_path: 1.0 + index for index, audio_path in enumerate(audio_paths)}

    monkeypatch.setattr(video, "audio_duration_seconds", lambda path: durations[path])

    lines = video.subtitle_lines(source, audio_paths=audio_paths)

    # Entry ono-001: clip-0 (dur=1.0) + clip-1 (dur=2.0) merged = 3.0s term frame
    # then zh_tw_meaning (clip-2, dur=3.0), then example_ja (clip-3, dur=4.0)
    # Entry ono-002: clip-4+clip-5 merged = 9.0+10.0? No: indices 4..7
    assert [line["text"] for line in lines[:3]] == [
        "しみじみ (しみじみ)",
        "深切地、由衷地；靜靜感受某種情緒",
        "卒業式で先生の言葉をしみじみと思い出した。\n（在畢業典禮上，我深深想起老師說過的話。）",
    ]
    # Term frame: dur=1.0+2.0=3.0 → end=3.0; zh_tw_meaning: start=3.6, dur=3.0 → end=6.6
    # example_ja: start=7.2, dur=4.0 → end=11.2
    assert round(lines[0]["start"], 1) == 0.0
    assert round(lines[0]["end"], 1) == 3.0
    assert round(lines[1]["start"], 1) == 3.6
    assert round(lines[2]["start"], 1) == 7.2
    assert all(current["end"] <= next_line["start"] for current, next_line in zip(lines, lines[1:]))


def test_write_video_with_audio_places_mp3_inputs_on_duration_driven_timeline(tmp_path, monkeypatch):
    source = load_source(SAMPLE)
    # New pipeline: 4 clips per entry (term1, term2, zh_tw_meaning, example_ja) × 2 entries = 8
    audio_paths = [tmp_path / "audio" / f"clip-{index}.mp3" for index in range(8)]
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

    output = video.write_video_file(source, tmp_path, audio_paths=audio_paths)

    assert output == tmp_path / "video.mp4"
    # calls[0] and calls[1] create silence files; calls[2] runs concat demuxer;
    # calls[3] is the final ffmpeg encode.
    assert len(calls) == 4
    # The last call is the final encode with -map 0:v / -map 1:a (no filter_complex)
    final_cmd, final_kwargs = calls[3]
    assert "-filter_complex" not in final_cmd
    assert final_cmd[final_cmd.index("-map") + 1] == "0:v"
    assert final_cmd[final_cmd.index("-map", final_cmd.index("-map") + 1) + 1] == "1:a"
    assert final_kwargs["check"] is True
    # Concat demuxer call (calls[2])
    concat_cmd, _ = calls[2]
    assert "-f" in concat_cmd
    assert "concat" in concat_cmd
    # The concat.txt file should list clips in order: term1, term2 (no gap), silence,
    # zh_tw_meaning, silence, example_ja, silence — repeated for entry 2
    concat_txt = tmp_path / "concat.txt"
    assert concat_txt.exists()
    concat_lines = concat_txt.read_text(encoding="utf-8").splitlines()
    # clip-0 and clip-1 (term1 + term2) appear consecutively without silence between them
    assert any("clip-0" in line for line in concat_lines)
    assert any("clip-1" in line for line in concat_lines)
    term_idx_0 = next(i for i, l in enumerate(concat_lines) if "clip-0" in l)
    term_idx_1 = next(i for i, l in enumerate(concat_lines) if "clip-1" in l)
    assert term_idx_1 == term_idx_0 + 1  # directly consecutive, no silence between


def test_build_video_assets_without_ffmpeg_still_writes_text_assets(tmp_path, monkeypatch):
    source = load_source(SAMPLE)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    assets = build_video_assets(source, tmp_path, make_video=True)

    assert assets["narration"].exists()
    assert assets["subtitles"].exists()
    assert assets["video"] is None
    assert not ffmpeg_available()


def test_video_assets_with_custom_repetition(tmp_path, monkeypatch):
    source = load_source(SAMPLE)
    # With 3 repetitions: 2 entries × (3 term + 1 meaning + 1 example) = 10 clips
    audio_paths = [tmp_path / "audio" / f"clip-{index}.mp3" for index in range(10)]
    audio_paths[0].parent.mkdir()
    for audio_path in audio_paths:
        audio_path.write_bytes(b"audio")
    durations = {audio_path: 1.0 for audio_path in audio_paths}

    monkeypatch.setattr(video, "audio_duration_seconds", lambda path: durations[path])

    # Check timeline_items
    items = video.timeline_items(source, audio_paths=audio_paths, word_repetition=3)
    # Entry 1 term should combine clip-0, clip-1, clip-2 (each dur=1.0) -> duration=3.0
    assert items[0]["duration"] == 3.0
    assert len(items[0]["audio_paths"]) == 3
    assert items[0]["audio_paths"] == audio_paths[0:3]

    # Verify concat call writes 3 consecutive files
    calls = []
    def capture_run(command, **kwargs):
        calls.append((command, kwargs))

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(video.subprocess, "run", capture_run)

    output = video.write_video_file(source, tmp_path, audio_paths=audio_paths, word_repetition=3)
    assert output == tmp_path / "video.mp4"

    concat_txt = tmp_path / "concat.txt"
    assert concat_txt.exists()
    concat_lines = concat_txt.read_text(encoding="utf-8").splitlines()

    # Verify that clip-0, clip-1, clip-2 appear directly after each other
    idx0 = next(i for i, l in enumerate(concat_lines) if "clip-0" in l)
    idx1 = next(i for i, l in enumerate(concat_lines) if "clip-1" in l)
    idx2 = next(i for i, l in enumerate(concat_lines) if "clip-2" in l)
    assert idx1 == idx0 + 1
    assert idx2 == idx1 + 1


def test_write_short_videos_splits_entries_and_audio_by_word_count(tmp_path, monkeypatch):
    source = load_source(SAMPLE)
    audio_paths = [tmp_path / "audio" / f"clip-{index}.mp3" for index in range(8)]
    audio_paths[0].parent.mkdir()
    for audio_path in audio_paths:
        audio_path.write_bytes(b"audio")
    durations = {audio_path: 1.0 for audio_path in audio_paths}
    calls = []

    def capture_run(command, **kwargs):
        calls.append((command, kwargs))

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(video, "audio_duration_seconds", lambda path: durations[path])
    monkeypatch.setattr(video.subprocess, "run", capture_run)

    outputs = write_short_videos(source, tmp_path, words_per_short=1, audio_paths=audio_paths)

    assert outputs == [
        tmp_path / "shorts" / "short_001" / "video.mp4",
        tmp_path / "shorts" / "short_002" / "video.mp4",
    ]
    first_subtitles = (tmp_path / "shorts" / "short_001" / "subtitles.ass").read_text(encoding="utf-8")
    second_subtitles = (tmp_path / "shorts" / "short_002" / "subtitles.ass").read_text(encoding="utf-8")
    assert "しみじみ" in first_subtitles
    assert "ぐずぐず" not in first_subtitles
    assert "ぐずぐず" in second_subtitles

    first_concat = (tmp_path / "shorts" / "short_001" / "concat.txt").read_text(encoding="utf-8")
    second_concat = (tmp_path / "shorts" / "short_002" / "concat.txt").read_text(encoding="utf-8")
    assert "clip-0" in first_concat
    assert "clip-3" in first_concat
    assert "clip-4" not in first_concat
    assert "clip-4" in second_concat
    assert "clip-7" in second_concat


def test_write_short_videos_rejects_invalid_word_count(tmp_path):
    source = load_source(SAMPLE)

    try:
        write_short_videos(source, tmp_path, words_per_short=0)
    except ValueError as error:
        assert "at least 1" in str(error)
    else:
        raise AssertionError("Expected ValueError")


def test_write_video_portrait_mode(tmp_path, monkeypatch):
    """Test that portrait mode produces 1080x1920 resolution in ASS output."""
    from jlpt_pipeline.models import active_entries

    source = load_source(SAMPLE)
    config = VideoFieldConfig()
    entries = active_entries(source)

    audio_paths_dict = {
        (str(entry["id"]), kind): [tmp_path / f"audio_{entry['id']}_{kind}.wav"]
        for entry in entries
        for kind in ["term", "zh_tw_meaning", "example_ja"]
    }

    # Create dummy audio files
    for path_list in audio_paths_dict.values():
        for p in path_list:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"dummy")

    # Monkeypatch audio_duration_seconds to avoid needing ffprobe
    monkeypatch.setattr(video, "audio_duration_seconds", lambda path: 1.5)

    result = write_video(
        source,
        tmp_path,
        audio_paths_dict,
        config,
        portrait=True,
        example_style=EXAMPLE_STYLE_SENTENCE,
    )

    # Verify it's a Path
    assert isinstance(result, Path)

    # Verify ASS file contains portrait dimensions
    ass_file = tmp_path / "narration.ass"
    assert ass_file.exists()
    content = ass_file.read_text()
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    assert "Style: Term,Noto Sans CJK JP,80," in content
    assert "Style: Body,Noto Sans CJK JP,52," in content


def test_write_video_landscape_mode(tmp_path, monkeypatch):
    """Test that landscape (default) mode produces 1920x1080 resolution in ASS output."""
    from jlpt_pipeline.models import active_entries

    source = load_source(SAMPLE)
    config = VideoFieldConfig()
    entries = active_entries(source)

    audio_paths_dict = {
        (str(entry["id"]), kind): [tmp_path / f"audio_{entry['id']}_{kind}.wav"]
        for entry in entries
        for kind in ["term", "zh_tw_meaning", "example_ja"]
    }

    for path_list in audio_paths_dict.values():
        for p in path_list:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"dummy")

    monkeypatch.setattr(video, "audio_duration_seconds", lambda path: 1.5)

    result = write_video(
        source,
        tmp_path,
        audio_paths_dict,
        config,
        portrait=False,
        example_style=EXAMPLE_STYLE_SENTENCE,
    )

    assert isinstance(result, Path)

    ass_file = tmp_path / "narration.ass"
    assert ass_file.exists()
    content = ass_file.read_text()
    assert "PlayResX: 1920" in content
    assert "PlayResY: 1080" in content
    assert "Style: Term,Noto Sans CJK JP,128," in content
    assert "Style: Body,Noto Sans CJK JP,76," in content


def test_write_video_uses_dict_audio_lookup_by_entry_id_and_kind(tmp_path, monkeypatch):
    """Test that write_video() correctly looks up audio by (entry_id, kind) key."""
    from jlpt_pipeline.models import active_entries

    source = load_source(SAMPLE)
    config = VideoFieldConfig(term_count=1, meaning_count=1, example_count=1)
    entries = active_entries(source)

    # Only provide audio for the first entry term - other entries get no audio
    first_entry_id = str(entries[0]["id"])
    audio_paths_dict: dict[tuple[str, str], list[Path]] = {
        (first_entry_id, "term"): [tmp_path / "term.wav"],
        (first_entry_id, "zh_tw_meaning"): [tmp_path / "meaning.wav"],
        (first_entry_id, "example_ja"): [tmp_path / "example.wav"],
    }

    for path_list in audio_paths_dict.values():
        for p in path_list:
            p.write_bytes(b"dummy")

    monkeypatch.setattr(video, "audio_duration_seconds", lambda path: 2.0)

    result = write_video(
        source,
        tmp_path,
        audio_paths_dict,
        config,
    )

    assert isinstance(result, Path)
    ass_file = tmp_path / "narration.ass"
    assert ass_file.exists()
    content = ass_file.read_text()
    # First entry's term should appear
    assert "しみじみ" in content
