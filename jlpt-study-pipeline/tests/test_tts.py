import hashlib
from dataclasses import fields
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "source.sample.json"
sys.path.insert(0, str(ROOT / "scripts"))

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
from jlpt_pipeline.validation import load_source


def test_tts_items_include_japanese_and_zh_tw_video_voice_fields():
    source = load_source(SAMPLE)

    items = tts_items(source)

    assert [item.kind for item in items[:4]] == [
        "term",
        "zh_tw_meaning",
        "example_ja",
        "example_zh_tw",
    ]
    assert {item.kind for item in items} == {
        "term",
        "zh_tw_meaning",
        "example_ja",
        "example_zh_tw",
    }
    assert [field.name for field in fields(TtsItem)] == [
        "entry_id",
        "kind",
        "text",
        "voice",
    ]
    assert items[0].voice == DEFAULT_VOICE
    assert items[1].voice == DEFAULT_ZH_TW_VOICE
    assert items[2].voice == DEFAULT_VOICE
    assert items[3].voice == DEFAULT_ZH_TW_VOICE


def test_estimate_tts_chars_skips_rejected_entries():
    source = load_source(SAMPLE)

    estimate = estimate_tts_chars(source)

    assert estimate.total_chars > 0
    assert estimate.items
    assert "ざあざあ" not in [item.text for item in estimate.items]


def test_audio_paths_for_source_returns_paths_in_tts_item_order(tmp_path):
    source = load_source(SAMPLE)

    paths = audio_paths_for_source(source, tmp_path, voice="ja-JP-NanamiNeural")

    assert [path.parent for path in paths] == [tmp_path / "audio"] * 8
    expected_names = [
        hashlib.sha1(f"{item.voice}:{item.text}".encode("utf-8")).hexdigest()
        + ".mp3"
        for item in tts_items(source)
    ]
    assert [path.name for path in paths] == expected_names


def test_default_provider_is_edge():
    assert DEFAULT_PROVIDER == "edge"
    assert DEFAULT_VOICE == "ja-JP-NanamiNeural"
    assert DEFAULT_ZH_TW_VOICE == "zh-TW-HsiaoChenNeural"


def test_synthesize_entries_none_provider_creates_audio_and_skips_items(tmp_path):
    source = load_source(SAMPLE)

    result = synthesize_entries(source, tmp_path, provider="none")

    assert (tmp_path / "audio").is_dir()
    assert result.generated == []
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
    assert result.skipped == 0
    assert len(result.generated) == 8
    assert all(path.read_bytes() == b"edge-audio" for path in result.generated)
    assert calls[0]["command"][:5] == [
        "edge-tts",
        "--voice",
        "ja-JP-NanamiNeural",
        "--text",
        "しみじみ",
    ]
    assert calls[1]["command"][:5] == [
        "edge-tts",
        "--voice",
        "zh-TW-HsiaoChenNeural",
        "--text",
        "深切地、由衷地；靜靜感受某種情緒",
    ]
    assert "--write-media" in calls[0]["command"]
    assert calls[0]["check"] is True
    assert calls[0]["capture_output"] is True
    assert calls[0]["text"] is True


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

    assert len(first.generated) == 8
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
    assert result.skipped == 8
    assert len(result.errors) == 8
    assert all("edge failed" in error for error in result.errors)


def test_edge_tts_missing_command_continues_and_skips(tmp_path, monkeypatch):
    source = load_source(SAMPLE)

    def fake_run(command, check, capture_output, text):
        raise FileNotFoundError("edge-tts")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = synthesize_entries(source, tmp_path, provider="edge")

    assert result.generated == []
    assert result.skipped == 8
    assert len(result.errors) == 8
    assert all("edge-tts command not found" in error for error in result.errors)
