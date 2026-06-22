import hashlib
from dataclasses import fields
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "source.sample.json"
sys.path.insert(0, str(ROOT / "scripts"))

import jlpt_pipeline.tts as tts
from jlpt_pipeline.tts import (
    DEFAULT_PROVIDER,
    DEFAULT_VOICE,
    DEFAULT_ZH_TW_VOICE,
    TtsItem,
    TtsResult,
    audio_paths_for_source,
    estimate_tts_chars,
    synthesize_entries,
    tts_items,
)
from jlpt_pipeline.models import VideoFieldConfig, active_entries
from jlpt_pipeline.validation import load_source


def test_tts_items_include_japanese_and_zh_tw_video_voice_fields():
    source = load_source(SAMPLE)

    items = tts_items(source)

    # New order per entry: term, term, zh_tw_meaning, example_ja
    # (example_zh_tw is shown inline on the example_ja frame; no separate audio)
    assert [item.kind for item in items[:4]] == [
        "term",
        "term",
        "zh_tw_meaning",
        "example_ja",
    ]
    assert {item.kind for item in items} == {
        "term",
        "zh_tw_meaning",
        "example_ja",
    }
    assert [field.name for field in fields(TtsItem)] == [
        "entry_id",
        "kind",
        "text",
        "voice",
    ]
    assert items[0].voice == DEFAULT_VOICE
    assert items[1].voice == DEFAULT_VOICE
    assert items[1].text == items[0].text
    assert items[2].voice == DEFAULT_ZH_TW_VOICE
    assert items[3].voice == DEFAULT_VOICE


def test_estimate_tts_chars_skips_rejected_entries():
    source = load_source(SAMPLE)

    estimate = estimate_tts_chars(source)

    assert estimate.total_chars > 0
    assert estimate.items
    assert "ざあざあ" not in [item.text for item in estimate.items]


def test_audio_paths_for_source_returns_paths_in_tts_item_order(tmp_path):
    source = load_source(SAMPLE)

    paths_dict = audio_paths_for_source(source, tmp_path, voice="ja-JP-NanamiNeural")

    # Should return a dict
    assert isinstance(paths_dict, dict)

    # Flatten all paths from the dict in tts_items order to verify audio dir
    all_paths = [path for paths in paths_dict.values() for path in paths]
    # 2 active entries × 4 items each (term×2, zh_tw_meaning, example_ja) = 8 total
    assert len(all_paths) == 8
    assert all(path.parent == tmp_path / "audio" for path in all_paths)

    # Verify each path corresponds to expected hash
    items = tts_items(source)
    expected_names = [
        hashlib.sha1(f"{item.voice}:{item.text}".encode("utf-8")).hexdigest()
        + ".mp3"
        for item in items
    ]
    actual_names_in_order = [path.name for paths in paths_dict.values() for path in paths]
    assert actual_names_in_order == expected_names


def test_default_provider_is_edge():
    assert DEFAULT_PROVIDER == "edge"
    assert DEFAULT_VOICE == "ja-JP-NanamiNeural"
    assert DEFAULT_ZH_TW_VOICE == "zh-TW-HsiaoChenNeural"


def test_edge_tts_command_resolves_from_active_virtualenv(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    edge_tts = bin_dir / "edge-tts"
    edge_tts.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(tts.shutil, "which", lambda name: None)
    monkeypatch.setattr(tts.sys, "executable", str(bin_dir / "python"))

    assert tts._edge_tts_command() == str(edge_tts)


def test_synthesize_entries_none_provider_creates_audio_and_skips_items(tmp_path):
    source = load_source(SAMPLE)

    result = synthesize_entries(source, tmp_path, provider="none")

    assert (tmp_path / "audio").is_dir()
    assert result.generated == []
    # 2 active entries × 4 items each = 8
    assert result.skipped == 8
    assert result.errors == []
    assert list((tmp_path / "audio").iterdir()) == []


def test_tts_result_generated_and_unsupported_provider_error(tmp_path):
    source = load_source(SAMPLE)

    blank = TtsResult()
    result = synthesize_entries(source, tmp_path, provider="bogus")

    assert blank.generated == []
    assert result.generated == []
    assert result.skipped == 0
    assert result.errors == ["unknown tts provider: bogus"]


def test_synthesize_entries_max_chars_error_generates_nothing(tmp_path):
    source = load_source(SAMPLE)

    result = synthesize_entries(source, tmp_path, provider="edge", max_chars=1)

    assert result.generated == []
    assert result.skipped == 0
    assert any("max tts chars" in error for error in result.errors)
    assert list((tmp_path / "audio").iterdir()) == []


def test_edge_tts_success_writes_files_and_uses_expected_command(tmp_path, monkeypatch):
    source = load_source(SAMPLE)
    calls = []

    def fake_run(command, check, capture_output, text):
        calls.append(
            {
                "command": command,
                "check": check,
                "capture_output": capture_output,
                "text": text,
            }
        )
        output = Path(command[command.index("--write-media") + 1])
        output.write_bytes(b"edge-audio")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = synthesize_entries(source, tmp_path, provider="edge", voice="ja-JP-NanamiNeural")

    assert result.errors == []
    # With parallel TTS execution: 8 items, the two term repetitions per entry
    # may both attempt to write the same hash file; typically 7 generated, 1 skipped.
    assert result.skipped + len(result.generated) == 8
    assert result.skipped >= 1  # at least the second term repetition is deduplicated
    assert all(path.read_bytes() == b"edge-audio" for path in result.generated)
    # At least one call uses the Japanese voice with the first term
    assert any(
        c["command"][1:5] == ["--voice", "ja-JP-NanamiNeural", "--text", "しみじみ"]
        for c in calls
    )
    # At least one call uses the Chinese voice
    assert any(c["command"][2] == "zh-TW-HsiaoChenNeural" for c in calls)
    assert all(c["check"] is True for c in calls)
    assert all(c["capture_output"] is True for c in calls)
    assert all(c["text"] is True for c in calls)
    assert all("--write-media" in c["command"] for c in calls)


def test_edge_tts_cache_skips_existing_outputs(tmp_path, monkeypatch):
    source = load_source(SAMPLE)
    calls = []

    def fake_run(command, check, capture_output, text):
        calls.append(command)
        output = Path(command[command.index("--write-media") + 1])
        output.write_bytes(b"edge-audio")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    first = synthesize_entries(source, tmp_path, provider="edge", use_cache=True)
    calls.clear()
    second = synthesize_entries(source, tmp_path, provider="edge", use_cache=True)

    # first run: 8 total items; at least 1 cache hit from term dedup; second run: all skipped
    assert len(first.generated) + first.skipped == 8
    assert len(first.generated) >= 6  # at minimum 3 unique per entry × 2 entries
    assert second.generated == []
    assert second.skipped == 8
    assert second.errors == []
    assert calls == []


def test_edge_tts_command_failure_continues_and_skips(tmp_path, monkeypatch):
    source = load_source(SAMPLE)

    def fake_run(command, check, capture_output, text):
        raise subprocess.CalledProcessError(
            returncode=2,
            cmd=command,
            stderr="edge failed",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = synthesize_entries(source, tmp_path, provider="edge")

    assert result.generated == []
    # 2 active entries × 4 items = 8; term is deduplicated to 1 unique call each,
    # so 2 entries × (1 unique term + 2 others) = 6 total unique items attempted
    assert result.skipped == 8
    assert len(result.errors) == 6
    assert all("edge failed" in error for error in result.errors)


def test_edge_tts_missing_command_continues_and_skips(tmp_path, monkeypatch):
    source = load_source(SAMPLE)

    def fake_run(command, check, capture_output, text):
        raise FileNotFoundError("edge-tts")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = synthesize_entries(source, tmp_path, provider="edge")

    assert result.generated == []
    assert result.skipped == 8
    assert len(result.errors) == 6
    assert all("edge-tts command not found" in error for error in result.errors)


def test_tts_uses_kana_instead_of_kanji_term():
    source = {
        "metadata": {"topic": "test", "verification_policy": "reviewed"},
        "entries": [
            {
                "id": "test-001",
                "term": "施錠",
                "kana": "せじょう",
                "zh_tw_meaning": "上鎖",
                "example_ja": "施錠してください",
                "verification_status": "reviewed",
            }
        ]
    }
    items = tts_items(source)
    # The term items should use the pronunciation (kana) "せじょう" instead of the kanji "施錠"
    assert items[0].text == "せじょう"
    assert items[1].text == "せじょう"
    # example_ja remains intact
    assert items[3].text == "施錠してください"


def test_tts_items_with_custom_repetition():
    source = {
        "metadata": {"topic": "test", "verification_policy": "reviewed"},
        "entries": [
            {
                "id": "test-001",
                "term": "施錠",
                "kana": "せじょう",
                "zh_tw_meaning": "上鎖",
                "example_ja": "施錠してください",
                "verification_status": "reviewed",
            }
        ]
    }
    # 3 repetitions
    items_3 = tts_items(source, word_repetition=3)
    assert len(items_3) == 5  # 3 terms + 1 meaning + 1 example
    assert [item.kind for item in items_3] == ["term", "term", "term", "zh_tw_meaning", "example_ja"]
    assert items_3[0].text == "せじょう"
    assert items_3[1].text == "せじょう"
    assert items_3[2].text == "せじょう"

    # 1 repetition
    items_1 = tts_items(source, word_repetition=1)
    assert len(items_1) == 3  # 1 term + 1 meaning + 1 example
    assert [item.kind for item in items_1] == ["term", "zh_tw_meaning", "example_ja"]

    # 0 repetitions
    items_0 = tts_items(source, word_repetition=0)
    assert len(items_0) == 2  # 0 terms + 1 meaning + 1 example
    assert [item.kind for item in items_0] == ["zh_tw_meaning", "example_ja"]


def test_tts_items_with_video_field_config():
    source = load_source(SAMPLE)
    config = VideoFieldConfig(term_count=3, meaning_count=1, example_count=1)

    items = tts_items(source, config=config)

    # With term_count=3, should have 3 term entries per vocabulary
    # Default order: term(1), meaning(2), example(3)
    # So for first entry: term, term, term, meaning, example
    assert items[0].kind == "term"
    assert items[1].kind == "term"
    assert items[2].kind == "term"
    assert items[3].kind == "zh_tw_meaning"
    assert items[4].kind == "example_ja"


def test_audio_paths_for_source_returns_dict():
    source = load_source(SAMPLE)
    out_dir = Path("/tmp/test_audio")
    config = VideoFieldConfig(term_count=2, meaning_count=1, example_count=1)

    paths_dict = audio_paths_for_source(source, out_dir, config=config)

    # Should return dict with keys like ("entry_id", "term"), ("entry_id", "meaning"), etc.
    assert isinstance(paths_dict, dict)

    # Get first entry id from source
    first_entry_id = str(active_entries(source)[0]["id"])

    # Should have keys for term, meaning, example
    assert (first_entry_id, "term") in paths_dict
    assert (first_entry_id, "zh_tw_meaning") in paths_dict
    assert (first_entry_id, "example_ja") in paths_dict

    # Values should be lists of Path
    assert isinstance(paths_dict[(first_entry_id, "term")], list)
    assert all(isinstance(p, Path) for p in paths_dict[(first_entry_id, "term")])


def test_estimate_tts_chars_with_config():
    source = load_source(SAMPLE)
    config = VideoFieldConfig(term_count=3, meaning_count=2, example_count=1)

    estimate = estimate_tts_chars(source, config=config)

    # Estimate should reflect the new counts
    items = estimate.items

    # Count term items for first entry
    first_entry_id = str(active_entries(source)[0]["id"])
    term_items = [item for item in items if item.entry_id == first_entry_id and item.kind == "term"]
    assert len(term_items) == 3

    meaning_items = [item for item in items if item.entry_id == first_entry_id and item.kind == "zh_tw_meaning"]
    assert len(meaning_items) == 2
