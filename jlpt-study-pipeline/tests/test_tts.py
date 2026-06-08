from copy import deepcopy
from dataclasses import fields
import sys
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "source.sample.json"
sys.path.insert(0, str(ROOT / "scripts"))

from jlpt_pipeline.tts import (
    TtsItem,
    TtsResult,
    estimate_tts_chars,
    synthesize_entries,
    tts_items,
)
from jlpt_pipeline.validation import load_source


class FakeResponse:
    def __init__(self, status_code=200, content=b"mp3", text=""):
        self.status_code = status_code
        self.content = content
        self.text = text


def azure_env(monkeypatch):
    monkeypatch.setenv("AZURE_SPEECH_KEY", "test-key")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "eastus")


def test_tts_items_include_term_and_example_without_voice_field():
    source = load_source(SAMPLE)

    items = tts_items(source)

    assert {item.kind for item in items} == {"term", "example_ja"}
    assert [field.name for field in fields(TtsItem)] == ["entry_id", "kind", "text"]


def test_estimate_tts_chars_skips_rejected_entries():
    source = load_source(SAMPLE)

    estimate = estimate_tts_chars(source)

    assert estimate.total_chars > 0
    assert estimate.items
    assert "ざあざあ" not in [item.text for item in estimate.items]


def test_synthesize_entries_none_provider_creates_audio_and_skips_items(tmp_path):
    source = load_source(SAMPLE)

    result = synthesize_entries(source, tmp_path, provider="none")

    assert (tmp_path / "audio").is_dir()
    assert result.generated == []
    assert result.skipped == 4
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

    result = synthesize_entries(source, tmp_path, provider="none", max_chars=1)

    assert result.generated == []
    assert result.skipped == 0
    assert any("max tts chars" in error for error in result.errors)
    assert list((tmp_path / "audio").iterdir()) == []


def test_azure_missing_env_returns_errors_and_skips_all(tmp_path, monkeypatch):
    source = load_source(SAMPLE)
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)

    result = synthesize_entries(source, tmp_path, provider="azure")

    assert result.generated == []
    assert result.skipped == 4
    assert result.errors == [
        "AZURE_SPEECH_KEY and AZURE_SPEECH_REGION are required for Azure TTS"
    ]


def test_azure_request_happy_path_writes_files_and_uses_expected_request(
    tmp_path, monkeypatch
):
    source = deepcopy(load_source(SAMPLE))
    source["entries"][0]["term"] = "雨&風<'\""
    calls = []
    azure_env(monkeypatch)

    def fake_post(url, headers, data, timeout):
        calls.append({"url": url, "headers": headers, "data": data, "timeout": timeout})
        return FakeResponse(content=b"audio-bytes")

    monkeypatch.setattr(requests, "post", fake_post)

    result = synthesize_entries(source, tmp_path, provider="azure")

    assert result.errors == []
    assert result.skipped == 0
    assert len(result.generated) == 4
    assert all(path.read_bytes() == b"audio-bytes" for path in result.generated)
    assert calls[0]["url"] == "https://eastus.tts.speech.microsoft.com/cognitiveservices/v1"
    assert calls[0]["headers"]["X-Microsoft-OutputFormat"] == (
        "audio-24khz-48kbitrate-mono-mp3"
    )
    assert calls[0]["timeout"] == 30
    ssml = calls[0]["data"].decode("utf-8")
    assert "雨&amp;風&lt;&apos;&quot;" in ssml


def test_azure_cache_skips_existing_outputs(tmp_path, monkeypatch):
    source = load_source(SAMPLE)
    calls = []
    azure_env(monkeypatch)

    def fake_post(url, headers, data, timeout):
        calls.append(data)
        return FakeResponse(content=b"cached-audio")

    monkeypatch.setattr(requests, "post", fake_post)

    first = synthesize_entries(source, tmp_path, provider="azure", use_cache=True)
    calls.clear()
    second = synthesize_entries(source, tmp_path, provider="azure", use_cache=True)

    assert len(first.generated) == 4
    assert second.generated == []
    assert second.skipped == 4
    assert second.errors == []
    assert calls == []


def test_azure_http_error_continues_and_skips(tmp_path, monkeypatch):
    source = load_source(SAMPLE)
    azure_env(monkeypatch)

    def fake_post(url, headers, data, timeout):
        return FakeResponse(status_code=429, text="rate limited")

    monkeypatch.setattr(requests, "post", fake_post)

    result = synthesize_entries(source, tmp_path, provider="azure")

    assert result.generated == []
    assert result.skipped == 4
    assert len(result.errors) == 4
    assert all("429 rate limited" in error for error in result.errors)


def test_azure_request_exception_continues_and_skips(tmp_path, monkeypatch):
    source = load_source(SAMPLE)
    azure_env(monkeypatch)

    def fake_post(url, headers, data, timeout):
        raise requests.RequestException("network unavailable")

    monkeypatch.setattr(requests, "post", fake_post)

    result = synthesize_entries(source, tmp_path, provider="azure")

    assert result.generated == []
    assert result.skipped == 4
    assert len(result.errors) == 4
    assert all("network unavailable" in error for error in result.errors)
