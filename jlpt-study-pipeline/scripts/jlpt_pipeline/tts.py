from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import requests

from .models import active_entries

DEFAULT_VOICE = "ja-JP-NanamiNeural"


@dataclass(frozen=True)
class TtsItem:
    entry_id: str
    kind: str
    text: str

    @property
    def chars(self) -> int:
        return len(self.text)


@dataclass(frozen=True)
class TtsEstimate:
    total_chars: int
    items: list[TtsItem]


@dataclass
class TtsResult:
    generated: list[Path] = field(default_factory=list)
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def tts_items(source: dict[str, Any], voice: str = DEFAULT_VOICE) -> list[TtsItem]:
    items: list[TtsItem] = []
    for entry in active_entries(source):
        entry_id = str(entry["id"])
        items.append(TtsItem(entry_id, "term", str(entry["term"])))
        items.append(TtsItem(entry_id, "example_ja", str(entry["example_ja"])))
    return items


def estimate_tts_chars(source: dict[str, Any], voice: str = DEFAULT_VOICE) -> TtsEstimate:
    items = tts_items(source, voice=voice)
    return TtsEstimate(total_chars=sum(item.chars for item in items), items=items)


def synthesize_entries(
    source: dict[str, Any],
    out_dir: Path,
    provider: str = "azure",
    voice: str = DEFAULT_VOICE,
    max_chars: int | None = None,
) -> TtsResult:
    audio_dir = out_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    estimate = estimate_tts_chars(source, voice=voice)
    result = TtsResult()

    if max_chars is not None and estimate.total_chars > max_chars:
        result.errors.append(
            f"max tts chars exceeded: {estimate.total_chars} > {max_chars}"
        )
        return result

    if provider == "none":
        result.skipped = len(estimate.items)
        return result

    if provider == "azure":
        return _synthesize_azure(estimate.items, audio_dir, voice=voice)

    result.errors.append(f"unknown tts provider: {provider}")
    return result


def _synthesize_azure(
    items: list[TtsItem], audio_dir: Path, voice: str = DEFAULT_VOICE
) -> TtsResult:
    audio_dir.mkdir(parents=True, exist_ok=True)
    result = TtsResult()
    key = os.environ.get("AZURE_SPEECH_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION")
    if not key or not region:
        result.errors.append(
            "AZURE_SPEECH_KEY and AZURE_SPEECH_REGION are required for Azure TTS"
        )
        result.skipped = len(items)
        return result

    endpoint = (
        f"https://{region}.tts.speech.microsoft.com/"
        "cognitiveservices/v1"
    )
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-16khz-32kbitrate-mono-mp3",
    }

    for item in items:
        output = _cache_path(audio_dir, item, voice)
        if output.exists():
            result.skipped += 1
            continue

        ssml = (
            "<speak version='1.0' xml:lang='ja-JP'>"
            f"<voice name='{_escape_xml(voice)}'>"
            f"{_escape_xml(item.text)}"
            "</voice>"
            "</speak>"
        )
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                data=ssml.encode("utf-8"),
                timeout=30,
            )
        except requests.RequestException as error:
            result.errors.append(
                f"Azure TTS failed for {item.entry_id}:{item.kind}: {error}"
            )
            result.skipped += 1
            continue
        if response.status_code >= 400:
            result.errors.append(
                f"Azure TTS failed for {item.entry_id}:{item.kind}: "
                f"{response.status_code} {response.text}"
            )
            result.skipped += 1
            continue

        output.write_bytes(response.content)
        result.generated.append(output)

    return result


def _cache_path(audio_dir: Path, item: TtsItem, voice: str = DEFAULT_VOICE) -> Path:
    digest = hashlib.sha1(f"{voice}:{item.text}".encode("utf-8")).hexdigest()
    return audio_dir / f"{digest}.mp3"


def _escape_xml(value: Any) -> str:
    return escape(str(value), {"'": "&apos;", '"': "&quot;"})
