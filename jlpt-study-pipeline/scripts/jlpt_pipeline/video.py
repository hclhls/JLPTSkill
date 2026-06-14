from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from .models import active_entries

FALLBACK_ITEM_SECONDS = 2.5
AUDIO_GAP_SECONDS = 0.6
TRAILING_SECONDS = 0.6
# Defines (style, kind, text_fn) for each video segment.
# "term" appears only once visually but its audio is played twice consecutively.
# "example_ja" includes the Chinese translation as a bracketed subtitle line.
VIDEO_ITEM_FIELDS = [
    ("Term", "term", lambda entry: f"{entry['term']} ({entry['kana']})"),
    ("Body", "zh_tw_meaning", lambda entry: entry["zh_tw_meaning"]),
    ("Body", "example_ja", lambda entry: (
        f"{entry['example_ja']}\n（{entry['example_zh_tw']}）"
    )),
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


def ffmpeg_filter_path(path: Path) -> str:
    escaped = path.as_posix().replace("\\", r"\\")
    for char in ("'", ":", ",", "[", "]"):
        escaped = escaped.replace(char, f"\\{char}")
    return f"ass=filename='{escaped}'"


def write_narration(source: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "narration.txt"
    blocks: list[str] = []

    for entry in active_entries(source):
        blocks.append(
            "\n".join(
                [
                    f"{entry['id']} {entry['term']} ({entry['kana']})",
                    f"Meaning: {entry['zh_tw_meaning']}",
                    f"Example JA: {entry['example_ja']}",
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
    source: dict[str, Any], audio_paths: list[Path] | None = None
) -> list[dict[str, Any]]:
    """Build timeline items from source entries.

    The "term" field is shown as a single unbroken visual segment but its audio
    plays twice in a row (no silence gap between the two repetitions).
    The Chinese example translation is shown inline on the same frame as the
    Japanese example sentence and has no separate audio clip.
    """
    # audio_paths order (per entry): term_1, term_2, zh_tw_meaning, example_ja
    # (example_zh_tw audio is omitted from the pipeline)
    audio_iter = iter(audio_paths or [])
    current = 0.0
    items: list[dict[str, Any]] = []

    for entry in active_entries(source):
        for style, kind, text_for_entry in VIDEO_ITEM_FIELDS:
            if kind == "term":
                # Consume both term audio clips; combine their durations so
                # there is no visual gap between the two repetitions.
                audio1 = next(audio_iter, None)
                audio2 = next(audio_iter, None)
                dur1 = FALLBACK_ITEM_SECONDS
                dur2 = FALLBACK_ITEM_SECONDS
                if audio1 is not None and audio1.exists():
                    dur1 = max(audio_duration_seconds(audio1), 0.1)
                if audio2 is not None and audio2.exists():
                    dur2 = max(audio_duration_seconds(audio2), 0.1)
                # Combined duration: both clips back-to-back with no gap
                duration = dur1 + dur2
                end = current + duration
                items.append(
                    {
                        "start": current,
                        "end": end,
                        "style": style,
                        "kind": kind,
                        "text": text_for_entry(entry),
                        # Store both audio paths for concat
                        "audio_path": audio1,
                        "audio_path2": audio2,
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
                        "audio_path": audio_path,
                        "audio_path2": None,
                        "duration": duration,
                    }
                )
            current = end + AUDIO_GAP_SECONDS

    return items


def timeline_duration(source: dict[str, Any], audio_paths: list[Path] | None = None) -> float:
    items = timeline_items(source, audio_paths=audio_paths)
    if not items:
        return FALLBACK_ITEM_SECONDS + TRAILING_SECONDS
    return items[-1]["end"] + TRAILING_SECONDS


def subtitle_lines(
    source: dict[str, Any], audio_paths: list[Path] | None = None
) -> list[dict[str, Any]]:
    return [
        {
            "start": item["start"],
            "end": item["end"],
            "style": item["style"],
            "text": item["text"],
        }
        for item in timeline_items(source, audio_paths=audio_paths)
    ]


def write_subtitles(
    source: dict[str, Any], out_dir: Path, audio_paths: list[Path] | None = None
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "subtitles.ass"
    template = _template_env().get_template("video_scene.ass.j2")
    title = source.get("metadata", {}).get("topic") or "JLPT Study"
    output.write_text(
        template.render(title=title, lines=subtitle_lines(source, audio_paths=audio_paths)),
        encoding="utf-8",
    )
    return output


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def write_video(
    source: dict[str, Any], out_dir: Path, audio_paths: list[Path] | None = None
) -> Path | None:
    if not ffmpeg_available():
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    timed_audio = audio_paths or None
    subtitles = write_subtitles(source, out_dir, audio_paths=timed_audio)
    output = out_dir / "video.mp4"
    duration = timeline_duration(source, audio_paths=timed_audio)

    # Check if there are usable audio files
    usable_audio = [path for path in audio_paths or [] if path.exists()]

    if usable_audio:
        # Generate silence files matching the edge-tts format (24000Hz mono MP3)
        silence_06 = out_dir / "audio" / "silence_0.6.mp3"
        silence_25 = out_dir / "audio" / "silence_2.5.mp3"
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
        for item in timeline_items(source, audio_paths=timed_audio):
            if item["kind"] == "term":
                # Two back-to-back term clips with no silence gap between them
                ap1 = item.get("audio_path")
                ap2 = item.get("audio_path2")
                lines.append(
                    f"file '{ap1.resolve().as_posix()}'" if ap1 and ap1.exists()
                    else f"file '{silence_25.resolve().as_posix()}'"
                )
                lines.append(
                    f"file '{ap2.resolve().as_posix()}'" if ap2 and ap2.exists()
                    else f"file '{silence_25.resolve().as_posix()}'"
                )
            else:
                if item["audio_path"] is not None and item["audio_path"].exists():
                    lines.append(f"file '{item['audio_path'].resolve().as_posix()}'")
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
            ffmpeg_filter_path(subtitles),
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
            ffmpeg_filter_path(subtitles),
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


def write_silent_video(source: dict[str, Any], out_dir: Path) -> Path | None:
    return write_video(source, out_dir, audio_paths=None)


def build_video_assets(
    source: dict[str, Any],
    out_dir: Path,
    make_video: bool = False,
    audio_paths: list[Path] | None = None,
) -> dict[str, Path | None]:
    narration = write_narration(source, out_dir)
    subtitles = write_subtitles(source, out_dir, audio_paths=audio_paths)
    video = write_video(source, out_dir, audio_paths=audio_paths) if make_video else None
    return {"narration": narration, "subtitles": subtitles, "video": video}
