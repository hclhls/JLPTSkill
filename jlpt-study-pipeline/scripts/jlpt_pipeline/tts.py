from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import active_entries

DEFAULT_PROVIDER = "edge"
DEFAULT_VOICE = "ja-JP-NanamiNeural"
DEFAULT_ZH_TW_VOICE = "zh-TW-HsiaoChenNeural"


@dataclass(frozen=True)
class TtsItem:
    entry_id: str
    kind: str
    text: str
    voice: str

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


def tts_items(
    source: dict[str, Any],
    voice: str = DEFAULT_VOICE,
    zh_voice: str = DEFAULT_ZH_TW_VOICE,
) -> list[TtsItem]:
    items: list[TtsItem] = []
    for entry in active_entries(source):
        entry_id = str(entry["id"])
        items.append(TtsItem(entry_id, "term", str(entry["term"]), voice))
        items.append(
            TtsItem(entry_id, "zh_tw_meaning", str(entry["zh_tw_meaning"]), zh_voice)
        )
        items.append(TtsItem(entry_id, "example_ja", str(entry["example_ja"]), voice))
        items.append(
            TtsItem(entry_id, "example_zh_tw", str(entry["example_zh_tw"]), zh_voice)
        )
    return items


def estimate_tts_chars(source: dict[str, Any]) -> TtsEstimate:
    items = tts_items(source)
    return TtsEstimate(total_chars=sum(item.chars for item in items), items=items)


def audio_paths_for_source(
    source: dict[str, Any],
    out_dir: Path,
    voice: str = DEFAULT_VOICE,
    zh_voice: str = DEFAULT_ZH_TW_VOICE,
) -> list[Path]:
    audio_dir = out_dir / "audio"
    return [_cache_path(audio_dir, item) for item in tts_items(source, voice, zh_voice)]


def synthesize_entries(
    source: dict[str, Any],
    out_dir: Path,
    provider: str = DEFAULT_PROVIDER,
    voice: str = DEFAULT_VOICE,
    zh_voice: str = DEFAULT_ZH_TW_VOICE,
    max_chars: int | None = None,
    use_cache: bool = True,
) -> TtsResult:
    audio_dir = out_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    items = tts_items(source, voice, zh_voice)
    estimate = TtsEstimate(total_chars=sum(item.chars for item in items), items=items)
    result = TtsResult()

    if max_chars is not None and estimate.total_chars > max_chars:
        result.errors.append(
            f"max tts chars exceeded: {estimate.total_chars} > {max_chars}"
        )
        return result

    if provider == "none":
        result.skipped = len(estimate.items)
        return result

    if provider == "edge":
        return _synthesize_edge(estimate.items, audio_dir, use_cache=use_cache)

    result.errors.append(f"unknown tts provider: {provider}")
    return result


def _synthesize_edge(
    items: list[TtsItem],
    audio_dir: Path,
    use_cache: bool = True,
) -> TtsResult:
    audio_dir.mkdir(parents=True, exist_ok=True)
    result = TtsResult()

    for item in items:
        output = _cache_path(audio_dir, item)
        if use_cache and output.exists():
            result.skipped += 1
            continue

        command = [
            "edge-tts",
            "--voice",
            item.voice,
            "--text",
            item.text,
            "--write-media",
            str(output),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError:
            result.errors.append(
                f"edge-tts command not found for {item.entry_id}:{item.kind}"
            )
            result.skipped += 1
            continue
        except subprocess.CalledProcessError as error:
            detail = error.stderr or error.stdout or str(error)
            result.errors.append(
                f"edge-tts failed for {item.entry_id}:{item.kind}: {detail}"
            )
            result.skipped += 1
            continue

        if output.exists():
            result.generated.append(output)
        else:
            result.errors.append(
                f"edge-tts did not create audio for {item.entry_id}:{item.kind}"
            )
            result.skipped += 1

    return result


def _cache_path(audio_dir: Path, item: TtsItem) -> Path:
    digest = hashlib.sha1(f"{item.voice}:{item.text}".encode("utf-8")).hexdigest()
    return audio_dir / f"{digest}.mp3"
