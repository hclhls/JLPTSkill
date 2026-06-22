from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
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
    """Return TTS items for the pipeline.

    Order per entry:
      1. term (Japanese, spoken twice)
      2. term (Japanese, second repetition)
      3. zh_tw_meaning (Chinese)
      4. example_ja (Japanese)

    ``example_zh_tw`` is intentionally omitted: the Chinese translation is
    shown as a bracketed subtitle on the same frame as the Japanese example
    sentence and does not have its own audio clip.
    """
    items: list[TtsItem] = []
    for entry in active_entries(source):
        entry_id = str(entry["id"])
        term = str(entry["term"])
        items.append(TtsItem(entry_id, "term", term, voice))
        items.append(TtsItem(entry_id, "term", term, voice))
        items.append(
            TtsItem(entry_id, "zh_tw_meaning", str(entry["zh_tw_meaning"]), zh_voice)
        )
        items.append(TtsItem(entry_id, "example_ja", str(entry["example_ja"]), voice))
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
