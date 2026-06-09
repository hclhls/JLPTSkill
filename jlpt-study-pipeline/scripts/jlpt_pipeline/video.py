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
VIDEO_ITEM_FIELDS = [
    ("Term", "term", lambda entry: f"{entry['term']} ({entry['kana']})"),
    ("Body", "zh_tw_meaning", lambda entry: entry["zh_tw_meaning"]),
    ("Body", "example_ja", lambda entry: entry["example_ja"]),
    ("Body", "example_zh_tw", lambda entry: entry["example_zh_tw"]),
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
    audio_iter = iter(audio_paths or [])
    current = 0.0
    items: list[dict[str, Any]] = []

    for entry in active_entries(source):
        for style, kind, text_for_entry in VIDEO_ITEM_FIELDS:
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
    usable_audio = [path for path in audio_paths or [] if path.exists()]
    timed_audio = usable_audio or None
    subtitles = write_subtitles(source, out_dir, audio_paths=timed_audio)
    output = out_dir / "video.mp4"
    duration = timeline_duration(source, audio_paths=timed_audio)
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x111111:s=1920x1080:d={duration:.1f}",
    ]

    for path in usable_audio:
        command.extend(["-i", path.as_posix()])

    command.extend(["-vf", ffmpeg_filter_path(subtitles)])
    if usable_audio:
        delayed_streams = []
        filters = []
        for audio_index, item in enumerate(timeline_items(source, audio_paths=usable_audio), start=1):
            if item["audio_path"] is None or not item["audio_path"].exists():
                continue
            delay_ms = int(round(item["start"] * 1000))
            label = f"a{audio_index}"
            filters.append(f"[{audio_index}:a]adelay={delay_ms}|{delay_ms}[{label}]")
            delayed_streams.append(f"[{label}]")
        filters.append(
            f"{''.join(delayed_streams)}amix=inputs={len(delayed_streams)}:duration=longest:normalize=0[aout]"
        )
        command.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "0:v",
                "-map",
                "[aout]",
                "-c:a",
                "aac",
            ]
        )

    command.extend(
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            output.as_posix(),
        ]
    )
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
