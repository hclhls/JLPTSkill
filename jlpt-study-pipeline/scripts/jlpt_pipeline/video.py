from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from .models import active_entries, resolve_example, EXAMPLE_STYLE_SENTENCE


def _is_cjk(char: str) -> bool:
    """Check if character is CJK (Chinese, Japanese, Korean)."""
    code = ord(char)
    return (
        (0x4E00 <= code <= 0x9FFF) or  # CJK Unified Ideographs
        (0x3040 <= code <= 0x309F) or  # Hiragana
        (0x30A0 <= code <= 0x30FF) or  # Katakana
        (0x3100 <= code <= 0x312F)     # Bopomofo
    )


def _estimate_char_width(font_size: int) -> float:
    """Estimate average character width in pixels based on font size.

    Approximate formula: width ≈ font_size * 0.6 for monospaced/CJK fonts.
    """
    return font_size * 0.6


def wrap_text(
    text: str,
    style: str,
    max_width_px: int,
    font_size: int,
) -> str:
    """Wrap text to fit within max_width_px, inserting ASS newlines.

    For CJK text: wraps at character boundaries (no spaces in CJK).
    For Latin text: wraps at word boundaries.
    Mixed text: wraps at CJK char boundaries or Latin word boundaries.

    Args:
        text: Text to wrap
        style: ASS style name ("Term", "Body", etc.) - for future style-specific rules
        max_width_px: Maximum width in pixels
        font_size: Font size in points

    Returns:
        Text with \\N (ASS newline) inserted at wrap points
    """
    if not text:
        return text

    char_width = _estimate_char_width(font_size)
    max_chars_per_line = int(max_width_px / char_width)

    if max_chars_per_line <= 0:
        max_chars_per_line = 1

    lines: list[str] = []
    current_line: list[str] = []
    current_width = 0

    i = 0
    while i < len(text):
        char = text[i]

        if _is_cjk(char):
            # CJK character - check if it fits
            if current_width + 1 > max_chars_per_line:
                if current_line:
                    lines.append("".join(current_line))
                    current_line = []
                    current_width = 0

            current_line.append(char)
            current_width += 1
            i += 1
        elif char.isspace():
            # Space - start new line if needed
            if current_width > 0:
                lines.append("".join(current_line))
                current_line = []
                current_width = 0
            i += 1
        else:
            # Latin word - collect until space
            word_chars = []
            word_width = 0
            while i < len(text) and not text[i].isspace() and not _is_cjk(text[i]):
                word_chars.append(text[i])
                word_width += 1
                i += 1

            word = "".join(word_chars)

            # Check if word fits on current line
            if current_width + word_width > max_chars_per_line:
                if current_line:
                    lines.append("".join(current_line))
                    current_line = []
                    current_width = 0

            current_line.append(word)
            current_width += word_width

    if current_line:
        lines.append("".join(current_line))

    return r"\N".join(lines)


FALLBACK_ITEM_SECONDS = 2.5
AUDIO_GAP_SECONDS = 0.6
TRAILING_SECONDS = 0.6


def display_term_with_kana(entry: dict[str, Any]) -> str:
    term = str(entry["term"])
    kana = str(entry.get("kana") or "")
    if kana and kana != term:
        return f"{term}（{kana}）"
    return term


def get_term_text(entry: dict[str, Any]) -> str:
    if "term_in" in entry:
        return f"{entry['term_tr']} ({entry['kana_tr']}) （自動詞：{entry['term_in']} {entry['kana_in']}）"
    return f"{entry['term']} ({entry['kana']})"

def get_meaning_text(entry: dict[str, Any]) -> str:
    if "term_in" in entry:
        return f"{entry['zh_tw_meaning_tr']}（自動詞：{entry['zh_tw_meaning_in']}）"
    return entry["zh_tw_meaning"]

def get_example_text(entry: dict[str, Any], example_style: str = EXAMPLE_STYLE_SENTENCE) -> str:
    if "term_in" in entry:
        return f"他：{entry['example_ja_tr']}\n（{entry['example_zh_tw_tr']}）\n自：{entry['example_ja_in']}\n（{entry['example_zh_tw_in']}）"
    example_ja = resolve_example(entry, example_style)
    if "notes" in entry and entry["notes"]:
        return f"{example_ja}\n（{entry['example_zh_tw']}）\n備註：{entry['notes']}"
    res = f"{example_ja}\n（{entry['example_zh_tw']}）"
    if entry.get("note_extra"):
        res += f"\n【參考資料：{entry['note_extra']}】"
    elif entry.get("note"):
        res += f"\n【參考資料：{entry['note']}】"
    return res

VIDEO_ITEM_FIELDS = [
    ("Term", "term", get_term_text),
    ("Body", "zh_tw_meaning", get_meaning_text),
    ("Body", "example_ja", get_example_text),
]


def _template_env() -> Environment:
    root = Path(__file__).resolve().parents[2] / "templates"
    env = Environment(
        loader=FileSystemLoader(root),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["ass_time"] = ass_time
    env.filters["escape_ass"] = escape_ass
    return env


def ass_time(seconds: float) -> str:
    centiseconds = int(round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole_seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{whole_seconds:02}.{centiseconds:02}"


def escape_ass(text: Any) -> str:
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    return (
        normalized.replace("\\", "＼")
        .replace("\n", r"\N")
        .replace("{", "(")
        .replace("}", ")")
    )


def _escape_ass_filter_value(path: Path) -> str:
    escaped = path.as_posix().replace("\\", r"\\")
    for char in ("'", ":", ",", "[", "]"):
        escaped = escaped.replace(char, f"\\{char}")
    return escaped


def bundled_fonts_dir() -> Path | None:
    fonts_dir = Path(__file__).resolve().parents[2] / "assets" / "fonts"
    if any(fonts_dir.glob("*.otf")) or any(fonts_dir.glob("*.ttf")) or any(fonts_dir.glob("*.ttc")):
        return fonts_dir
    return None


def ffmpeg_filter_path(path: Path, fonts_dir: Path | None = None) -> str:
    escaped = _escape_ass_filter_value(path)
    filter_arg = f"ass=filename='{escaped}'"
    if fonts_dir is not None:
        filter_arg += f":fontsdir='{_escape_ass_filter_value(fonts_dir)}'"
    return filter_arg


def write_narration(
    source: dict[str, Any], out_dir: Path, example_style: str = EXAMPLE_STYLE_SENTENCE
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "narration.txt"
    blocks: list[str] = []

    for entry in active_entries(source):
        example_text = resolve_example(entry, example_style)
        blocks.append(
            "\n".join(
                [
                    f"{entry['id']} {display_term_with_kana(entry)}",
                    f"Meaning: {entry['zh_tw_meaning']}",
                    f"Example JA: {example_text}",
                    f"Example ZH: {entry['example_zh_tw']}",
                ]
            )
        )

    output.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return output


def audio_duration_seconds(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path.as_posix(),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return max(float(result.stdout.strip()), 0.0)


def timeline_items(
    source: dict[str, Any],
    audio_paths: list[Path] | None = None,
    example_style: str = EXAMPLE_STYLE_SENTENCE,
    word_repetition: int = 2,
) -> list[dict[str, Any]]:
    """Build timeline items from source entries.

    The "term" field is shown as a single unbroken visual segment but its audio
    plays `word_repetition` times in a row (no silence gap between the repetitions).
    The Chinese example translation is shown inline on the same frame as the
    Japanese example sentence and has no separate audio clip.
    """
    # Build a per-entry VIDEO_ITEM_FIELDS that uses the resolved example style
    def _fields_for_entry(entry: dict[str, Any]):
        return [
            ("Term", "term", get_term_text),
            ("Body", "zh_tw_meaning", get_meaning_text),
            ("Body", "example_ja", lambda e: get_example_text(e, example_style)),
        ]

    # audio_paths order (per entry): term_1, ..., term_N, zh_tw_meaning, example_ja
    # (example_zh_tw audio is omitted from the pipeline)
    audio_iter = iter(audio_paths or [])
    current = 0.0
    items: list[dict[str, Any]] = []

    for entry in active_entries(source):
        for style, kind, text_for_entry in _fields_for_entry(entry):
            if kind == "term":
                # Consume all term audio clips; combine their durations so
                # there is no visual gap between the repetitions.
                term_audios = []
                for _ in range(word_repetition):
                    term_audios.append(next(audio_iter, None))

                duration = 0.0
                if audio_paths is None:
                    # Silent video fallback or when no audio paths are provided at all
                    duration = max(word_repetition, 1) * FALLBACK_ITEM_SECONDS
                else:
                    for audio in term_audios:
                        dur = FALLBACK_ITEM_SECONDS
                        if audio is not None and audio.exists():
                            dur = max(audio_duration_seconds(audio), 0.1)
                        duration += dur

                end = current + duration
                items.append(
                    {
                        "start": current,
                        "end": end,
                        "style": style,
                        "kind": kind,
                        "text": text_for_entry(entry),
                        # Store all audio paths for concat
                        "audio_paths": term_audios,
                        "audio_path": term_audios[0] if len(term_audios) > 0 else None,
                        "audio_path2": term_audios[1] if len(term_audios) > 1 else None,
                        "duration": duration,
                    }
                )
            else:
                audio_path = next(audio_iter, None)
                duration = FALLBACK_ITEM_SECONDS
                if audio_path is not None and audio_path.exists():
                    duration = max(audio_duration_seconds(audio_path), 0.1)
                end = current + duration
                items.append(
                    {
                        "start": current,
                        "end": end,
                        "style": style,
                        "kind": kind,
                        "text": text_for_entry(entry),
                        "audio_paths": [audio_path] if audio_path is not None else [],
                        "audio_path": audio_path,
                        "audio_path2": None,
                        "duration": duration,
                    }
                )
            current = end + AUDIO_GAP_SECONDS

    return items


def timeline_duration(
    source: dict[str, Any],
    audio_paths: list[Path] | None = None,
    example_style: str = EXAMPLE_STYLE_SENTENCE,
    word_repetition: int = 2,
) -> float:
    items = timeline_items(source, audio_paths=audio_paths, example_style=example_style, word_repetition=word_repetition)
    if not items:
        return FALLBACK_ITEM_SECONDS + TRAILING_SECONDS
    return items[-1]["end"] + TRAILING_SECONDS


def subtitle_lines(
    source: dict[str, Any],
    audio_paths: list[Path] | None = None,
    example_style: str = EXAMPLE_STYLE_SENTENCE,
    word_repetition: int = 2,
) -> list[dict[str, Any]]:
    return [
        {
            "start": item["start"],
            "end": item["end"],
            "style": item["style"],
            "text": item["text"],
        }
        for item in timeline_items(source, audio_paths=audio_paths, example_style=example_style, word_repetition=word_repetition)
    ]


def write_subtitles(
    source: dict[str, Any],
    out_dir: Path,
    audio_paths: list[Path] | None = None,
    example_style: str = EXAMPLE_STYLE_SENTENCE,
    word_repetition: int = 2,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "subtitles.ass"
    template = _template_env().get_template("video_scene.ass.j2")
    title = source.get("metadata", {}).get("topic") or "JLPT Study"
    output.write_text(
        template.render(
            title=title,
            lines=subtitle_lines(source, audio_paths=audio_paths, example_style=example_style, word_repetition=word_repetition),
        ),
        encoding="utf-8",
    )
    return output


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _entry_audio_count(word_repetition: int) -> int:
    return max(word_repetition, 1) + 2


def _chunked(items: list[Any], chunk_size: int) -> list[list[Any]]:
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def _source_for_entries(source: dict[str, Any], entries: list[dict[str, Any]], part_index: int, part_count: int) -> dict[str, Any]:
    metadata = dict(source.get("metadata", {}))
    title = metadata.get("topic") or "JLPT Study"
    metadata["topic"] = f"{title} {part_index}/{part_count}"
    return {**source, "metadata": metadata, "entries": entries}


def write_video(
    source: dict[str, Any],
    out_dir: Path,
    audio_paths: list[Path] | None = None,
    example_style: str = EXAMPLE_STYLE_SENTENCE,
    word_repetition: int = 2,
) -> Path | None:
    if not ffmpeg_available():
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    timed_audio = audio_paths or None
    subtitles = write_subtitles(source, out_dir, audio_paths=timed_audio, example_style=example_style, word_repetition=word_repetition)
    fonts_dir = bundled_fonts_dir()
    output = out_dir / "video.mp4"
    duration = timeline_duration(source, audio_paths=timed_audio, example_style=example_style, word_repetition=word_repetition)

    # Check if there are usable audio files
    usable_audio = [path for path in audio_paths or [] if path.exists()]

    if usable_audio:
        # Generate silence files matching the edge-tts format (24000Hz mono MP3)
        silence_06 = out_dir / "audio" / "silence_0.6.mp3"
        silence_25 = out_dir / "audio" / "silence_2.5.mp3"
        silence_06.parent.mkdir(parents=True, exist_ok=True)
        if not silence_06.exists():
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "0.6", "-c:a", "libmp3lame", "-b:a", "48k", silence_06.as_posix()],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        if not silence_25.exists():
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "2.5", "-c:a", "libmp3lame", "-b:a", "48k", silence_25.as_posix()],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

        # Create concat.txt
        concat_txt = out_dir / "concat.txt"
        lines = []
        for item in timeline_items(source, audio_paths=timed_audio, example_style=example_style, word_repetition=word_repetition):
            if item["audio_paths"]:
                for ap in item["audio_paths"]:
                    if ap is not None and ap.exists():
                        lines.append(f"file '{ap.resolve().as_posix()}'")
                    else:
                        lines.append(f"file '{silence_25.resolve().as_posix()}'")
            else:
                lines.append(f"file '{silence_25.resolve().as_posix()}'")
            lines.append(f"file '{silence_06.resolve().as_posix()}'")

        concat_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Concatenate audio files using the concat demuxer.
        # We transcode the audio to WAV (PCM) rather than stream copying (-c copy)
        # to avoid MP3 encoder delay/padding drift, which causes cumulative desync.
        narration_combined = out_dir / "narration_combined.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt.as_posix(), narration_combined.as_posix()],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        command = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x111111:s=1920x1080:d={duration:.1f}",
            "-i",
            narration_combined.as_posix(),
            "-vf",
            ffmpeg_filter_path(subtitles, fonts_dir=fonts_dir),
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            output.as_posix(),
        ]
    else:
        # Fallback to silent video if no audio files are available
        command = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x111111:s=1920x1080:d={duration:.1f}",
            "-vf",
            ffmpeg_filter_path(subtitles, fonts_dir=fonts_dir),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            output.as_posix(),
        ]

    subprocess.run(
        command,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return output


def write_silent_video(
    source: dict[str, Any],
    out_dir: Path,
    example_style: str = EXAMPLE_STYLE_SENTENCE,
    word_repetition: int = 2,
) -> Path | None:
    return write_video(source, out_dir, audio_paths=None, example_style=example_style, word_repetition=word_repetition)


def build_video_assets(
    source: dict[str, Any],
    out_dir: Path,
    make_video: bool = False,
    audio_paths: list[Path] | None = None,
    example_style: str = EXAMPLE_STYLE_SENTENCE,
    word_repetition: int = 2,
    words_per_short: int | None = None,
) -> dict[str, Path | None]:
    narration = write_narration(source, out_dir, example_style=example_style)
    subtitles = write_subtitles(source, out_dir, audio_paths=audio_paths, example_style=example_style, word_repetition=word_repetition)
    video = None
    videos: list[Path] = []

    if make_video and words_per_short is not None:
        videos = write_short_videos(
            source,
            out_dir,
            words_per_short=words_per_short,
            audio_paths=audio_paths,
            example_style=example_style,
            word_repetition=word_repetition,
        )
    elif make_video:
        video = write_video(source, out_dir, audio_paths=audio_paths, example_style=example_style, word_repetition=word_repetition)

    return {"narration": narration, "subtitles": subtitles, "video": video, "videos": videos}


def write_short_videos(
    source: dict[str, Any],
    out_dir: Path,
    words_per_short: int,
    audio_paths: list[Path] | None = None,
    example_style: str = EXAMPLE_STYLE_SENTENCE,
    word_repetition: int = 2,
) -> list[Path]:
    if words_per_short < 1:
        raise ValueError("words_per_short must be at least 1")

    entries = active_entries(source)
    if not entries:
        return []

    entry_chunks = _chunked(entries, words_per_short)
    if audio_paths is None:
        audio_chunks: list[list[Path] | None] = [None for _ in entry_chunks]
    else:
        clips_per_entry = _entry_audio_count(word_repetition)
        audio_chunks = _chunked(audio_paths, words_per_short * clips_per_entry)

    videos: list[Path] = []
    part_count = len(entry_chunks)
    for index, entries_chunk in enumerate(entry_chunks, start=1):
        short_dir = out_dir / "shorts" / f"short_{index:03d}"
        short_source = _source_for_entries(source, entries_chunk, index, part_count)
        chunk_audio = audio_chunks[index - 1] if index - 1 < len(audio_chunks) else None
        video = write_video(
            short_source,
            short_dir,
            audio_paths=chunk_audio,
            example_style=example_style,
            word_repetition=word_repetition,
        )
        if video is not None:
            videos.append(video)
    return videos
