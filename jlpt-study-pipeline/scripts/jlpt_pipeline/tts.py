from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import VideoFieldConfig, active_entries, resolve_example, EXAMPLE_STYLE_SENTENCE

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
    example_style: str = EXAMPLE_STYLE_SENTENCE,
    word_repetition: int = 2,
    config: VideoFieldConfig | None = None,
) -> list[TtsItem]:
    """Return TTS items for the pipeline.

    If *config* is provided, field counts and ordering are taken from it and
    *word_repetition* is ignored.  When *config* is None (the default) the
    legacy behaviour is preserved: term repeated *word_repetition* times,
    then zh_tw_meaning, then example_ja.

    ``example_zh_tw`` is intentionally omitted: the Chinese translation is
    shown as a bracketed subtitle on the same frame as the Japanese example
    sentence and does not have its own audio clip.
    """
    if config is not None:
        return _tts_items_from_config(source, voice, zh_voice, example_style, config)

    items: list[TtsItem] = []
    for entry in active_entries(source):
        entry_id = str(entry["id"])
        # Use kana for TTS pronunciation of the term to avoid incorrect Kanji pronunciation
        term_tts_text = str(entry.get("kana") or entry["term"])
        for _ in range(word_repetition):
            items.append(TtsItem(entry_id, "term", term_tts_text, voice))
        items.append(
            TtsItem(entry_id, "zh_tw_meaning", str(entry["zh_tw_meaning"]), zh_voice)
        )
        items.append(TtsItem(entry_id, "example_ja", resolve_example(entry, example_style), voice))
    return items


def _tts_items_from_config(
    source: dict[str, Any],
    voice: str,
    zh_voice: str,
    example_style: str,
    config: VideoFieldConfig,
) -> list[TtsItem]:
    """Return TTS items ordered and repeated according to *config*."""
    items: list[TtsItem] = []
    for entry in active_entries(source):
        entry_id = str(entry["id"])
        term_tts_text = str(entry.get("kana") or entry["term"])

        field_data = {
            "term": {
                "count": config.term_count,
                "text": term_tts_text,
                "voice": voice,
                "kind": "term",
            },
            "meaning": {
                "count": config.meaning_count,
                "text": str(entry["zh_tw_meaning"]),
                "voice": zh_voice,
                "kind": "zh_tw_meaning",
            },
            "example": {
                "count": config.example_count,
                "text": resolve_example(entry, example_style),
                "voice": voice,
                "kind": "example_ja",
            },
        }

        for field_name, _ in config.ordered_fields():
            data = field_data[field_name]
            for _ in range(data["count"]):
                items.append(TtsItem(entry_id, data["kind"], data["text"], data["voice"]))

    return items


def estimate_tts_chars(
    source: dict[str, Any],
    example_style: str = EXAMPLE_STYLE_SENTENCE,
    word_repetition: int = 2,
    config: VideoFieldConfig | None = None,
) -> TtsEstimate:
    items = tts_items(source, example_style=example_style, word_repetition=word_repetition, config=config)
    return TtsEstimate(total_chars=sum(item.chars for item in items), items=items)


def audio_paths_for_source(
    source: dict[str, Any],
    out_dir: Path,
    voice: str = DEFAULT_VOICE,
    zh_voice: str = DEFAULT_ZH_TW_VOICE,
    example_style: str = EXAMPLE_STYLE_SENTENCE,
    word_repetition: int = 2,
    config: VideoFieldConfig | None = None,
) -> dict[tuple[str, str], list[Path]]:
    """Return a dict mapping (entry_id, kind) to list of audio paths.

    This allows flexible ordering of audio files independent of their cache position.
    """
    audio_dir = out_dir / "audio"
    items = tts_items(source, voice, zh_voice, example_style, word_repetition, config)

    result: dict[tuple[str, str], list[Path]] = {}
    for item in items:
        key = (item.entry_id, item.kind)
        path = _cache_path(audio_dir, item)
        if key not in result:
            result[key] = []
        result[key].append(path)

    return result


def synthesize_entries(
    source: dict[str, Any],
    out_dir: Path,
    provider: str = DEFAULT_PROVIDER,
    voice: str = DEFAULT_VOICE,
    zh_voice: str = DEFAULT_ZH_TW_VOICE,
    max_chars: int | None = None,
    use_cache: bool = True,
    example_style: str = EXAMPLE_STYLE_SENTENCE,
    word_repetition: int = 2,
) -> TtsResult:
    audio_dir = out_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    items = tts_items(source, voice, zh_voice, example_style, word_repetition)
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


def _edge_tts_command() -> str:
    executable = shutil.which("edge-tts")
    if executable:
        return executable

    venv_executable = Path(sys.executable).with_name("edge-tts")
    if venv_executable.exists():
        return str(venv_executable)

    return "edge-tts"


def _synthesize_item(
    item: TtsItem,
    audio_dir: Path,
    use_cache: bool,
) -> tuple[Path | None, str | None, bool]:
    output = _cache_path(audio_dir, item)
    if use_cache and output.exists():
        # If cache exists but has 0 bytes (corrupt), delete it so it gets regenerated
        if output.stat().st_size == 0:
            try:
                output.unlink()
            except Exception:
                pass
        else:
            return None, None, True

    command = [
        _edge_tts_command(),
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
        return None, f"edge-tts command not found for {item.entry_id}:{item.kind}", True
    except subprocess.CalledProcessError as error:
        detail = error.stderr or error.stdout or str(error)
        return None, f"edge-tts failed for {item.entry_id}:{item.kind}: {detail}", True

    if output.exists() and output.stat().st_size > 0:
        return output, None, False
    else:
        return None, f"edge-tts did not create valid audio for {item.entry_id}:{item.kind}", True


def _synthesize_edge(
    items: list[TtsItem],
    audio_dir: Path,
    use_cache: bool = True,
) -> TtsResult:
    from concurrent.futures import ThreadPoolExecutor
    
    audio_dir.mkdir(parents=True, exist_ok=True)
    result = TtsResult()

    # Deduplicate items by their cache path to avoid parallel race conditions and duplicate work
    unique_items = []
    seen_paths = set()
    skipped_count = 0
    for item in items:
        path = _cache_path(audio_dir, item)
        if path in seen_paths:
            skipped_count += 1
        else:
            seen_paths.add(path)
            unique_items.append(item)

    # Use 16 parallel threads to perform TTS synthesis on unique items
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [
            executor.submit(_synthesize_item, item, audio_dir, use_cache)
            for item in unique_items
        ]
        for future in futures:
            output, error, skipped = future.result()
            if skipped:
                result.skipped += 1
            if error:
                result.errors.append(error)
            if output:
                result.generated.append(output)

    result.skipped += skipped_count
    return result


def _cache_path(audio_dir: Path, item: TtsItem) -> Path:
    digest = hashlib.sha1(f"{item.voice}:{item.text}".encode("utf-8")).hexdigest()
    return audio_dir / f"{digest}.mp3"
