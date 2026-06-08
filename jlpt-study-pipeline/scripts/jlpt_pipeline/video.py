from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from .models import active_entries

SEGMENT_SECONDS = 12


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
                    f"Recall prompt: {entry['recall_prompt_zh_tw']}",
                    f"Answer: {entry['term']}",
                ]
            )
        )

    output.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return output


def subtitle_lines(source: dict[str, Any]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    timings = [
        ("Term", 0.0, 2.5, lambda entry: f"{entry['term']} ({entry['kana']})"),
        ("Body", 2.5, 4.5, lambda entry: entry["zh_tw_meaning"]),
        ("Body", 4.5, 7.0, lambda entry: entry["example_ja"]),
        ("Body", 7.0, 9.0, lambda entry: entry["example_zh_tw"]),
        ("Prompt", 9.0, 11.0, lambda entry: entry["recall_prompt_zh_tw"]),
        ("Term", 11.0, 12.0, lambda entry: entry["term"]),
    ]

    for index, entry in enumerate(active_entries(source)):
        offset = index * SEGMENT_SECONDS
        for style, start, end, text_for_entry in timings:
            lines.append(
                {
                    "start": offset + start,
                    "end": offset + end,
                    "style": style,
                    "text": text_for_entry(entry),
                }
            )
    return lines


def write_subtitles(source: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "subtitles.ass"
    template = _template_env().get_template("video_scene.ass.j2")
    title = source.get("metadata", {}).get("topic") or "JLPT Study"
    output.write_text(
        template.render(title=title, lines=subtitle_lines(source)),
        encoding="utf-8",
    )
    return output


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def write_silent_video(source: dict[str, Any], out_dir: Path) -> Path | None:
    if not ffmpeg_available():
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    subtitles = write_subtitles(source, out_dir)
    output = out_dir / "video.mp4"
    duration = max(len(active_entries(source)) * SEGMENT_SECONDS, SEGMENT_SECONDS)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x111111:s=1920x1080:d={duration}",
            "-vf",
            ffmpeg_filter_path(subtitles),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            output.as_posix(),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return output


def build_video_assets(
    source: dict[str, Any], out_dir: Path, make_video: bool = False
) -> dict[str, Path | None]:
    narration = write_narration(source, out_dir)
    subtitles = write_subtitles(source, out_dir)
    video = write_silent_video(source, out_dir) if make_video else None
    return {"narration": narration, "subtitles": subtitles, "video": video}
