from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .anki import write_anki_csv, write_anki_package
from .models import ValidationReport, EXAMPLE_STYLE_SENTENCE
from .obsidian import write_obsidian_markdown
from .tts import (
    DEFAULT_PROVIDER,
    DEFAULT_VOICE,
    DEFAULT_ZH_TW_VOICE,
    audio_paths_for_source,
    estimate_tts_chars,
    synthesize_entries,
)
from .validation import load_source, render_validation_report, validate_source
from .video import build_video_assets, ffmpeg_available


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    return args.command(args)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jlpt-pipeline")
    subcommands = parser.add_subparsers(required=True)

    validate = subcommands.add_parser("validate")
    _add_source_out_args(validate)
    _add_example_style_arg(validate)
    _add_word_repetition_arg(validate)
    validate.set_defaults(command=_validate_command)

    dry_run = subcommands.add_parser("dry-run")
    _add_source_out_args(dry_run)
    _add_example_style_arg(dry_run)
    _add_word_repetition_arg(dry_run)
    dry_run.set_defaults(command=_dry_run_command)

    build = subcommands.add_parser("build")
    _add_source_out_args(build)
    _add_example_style_arg(build)
    _add_word_repetition_arg(build)
    _add_video_words_per_short_arg(build)
    build.add_argument("--deck-name", required=True)
    build.add_argument(
        "--tts-provider",
        default=DEFAULT_PROVIDER,
        choices=["edge", "none"],
    )
    build.add_argument("--voice", default=DEFAULT_VOICE)
    build.add_argument("--zh-voice", default=DEFAULT_ZH_TW_VOICE)
    build.add_argument("--slug", default="jlpt-study")
    build.add_argument("--video", action="store_true")
    build.add_argument("--max-tts-chars", type=int)
    build.add_argument("--no-tts-cache", action="store_true")
    build.set_defaults(command=_build_command)

    return parser


def _add_source_out_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)


def _add_example_style_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--example-style",
        default=EXAMPLE_STYLE_SENTENCE,
        choices=["sentence", "phrase"],
        help=(
            "sentence: use the full Japanese example sentence (default); "
            "phrase: use the short vocabulary phrase (example_ja_phrase field, "
            "falls back to example_ja if the phrase field is absent)"
        ),
    )


def _add_word_repetition_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--word-repetition",
        default=2,
        type=int,
        help="Number of times the Japanese vocabulary is read out (default: 2)",
    )


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _add_video_words_per_short_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--video-words-per-short",
        type=_positive_int,
        help=(
            "Create multiple video outputs under shorts/ with this many active "
            "vocabulary entries per video. Omit to keep the original single long video."
        ),
    )


def _validate_command(args: argparse.Namespace) -> int:
    source = _load_source_or_write_report(args.source, args.out)
    if source is None:
        return 1

    report = validate_source(source)
    _write_report(args.out, render_validation_report(report))
    return 0 if report.ok else 1


def _dry_run_command(args: argparse.Namespace) -> int:
    source = _load_source_or_write_report(args.source, args.out)
    if source is None:
        return 1

    report = validate_source(source)
    if not report.ok:
        _write_report(args.out, render_validation_report(report))
        return 1

    estimate = estimate_tts_chars(source, example_style=args.example_style, word_repetition=args.word_repetition)
    report_text = _append_sections(
        render_validation_report(report),
        "Dry Run",
        [
            f"Estimated TTS characters: {estimate.total_chars}",
            f"Example style: {args.example_style}",
            f"Word repetition count: {args.word_repetition}",
        ],
    )
    _write_report(args.out, report_text)
    return 0 if report.ok else 1


def _build_command(args: argparse.Namespace) -> int:
    source = _load_source_or_write_report(args.source, args.out)
    if source is None:
        return 1

    report = validate_source(source)
    report_text = render_validation_report(report)
    if not report.ok:
        _write_report(args.out, report_text)
        return 1

    obsidian = write_obsidian_markdown(source, args.out, args.slug)
    anki_csv = write_anki_csv(source, args.out, example_style=args.example_style)
    anki_package = write_anki_package(source, args.out, args.deck_name, example_style=args.example_style)
    tts_result = synthesize_entries(
        source,
        args.out,
        provider=args.tts_provider,
        voice=args.voice,
        zh_voice=args.zh_voice,
        max_chars=args.max_tts_chars,
        use_cache=not args.no_tts_cache,
        example_style=args.example_style,
        word_repetition=args.word_repetition,
    )
    audio_paths = audio_paths_for_source(
        source, args.out, voice=args.voice, zh_voice=args.zh_voice,
        example_style=args.example_style,
        word_repetition=args.word_repetition,
    )
    video_assets: dict[str, Path | None] = {
        "narration": None,
        "subtitles": None,
        "video": None,
    }
    video_error = None
    try:
        video_assets = build_video_assets(
            source, args.out, make_video=args.video, audio_paths=audio_paths,
            example_style=args.example_style,
            word_repetition=args.word_repetition,
            words_per_short=args.video_words_per_short,
        )
    except Exception as error:
        video_error = str(error)

    output_lines = [
        f"- Obsidian markdown: {obsidian.name}",
        f"- Anki CSV: {anki_csv.name}",
        f"- Anki package: {anki_package.name}",
    ]
    if video_assets["narration"] is not None:
        output_lines.append(f"- Narration: {video_assets['narration'].name}")
    if video_assets["subtitles"] is not None:
        output_lines.append(f"- Subtitles: {video_assets['subtitles'].name}")
    if video_assets["video"] is not None:
        output_lines.append(f"- Video: {video_assets['video'].name}")
    for short_video in video_assets.get("videos", []):
        output_lines.append(f"- Short video: {short_video.relative_to(args.out)}")
    if video_error is not None:
        output_lines.append(f"- Warning: video assets failed: {video_error}")
    elif args.video and not ffmpeg_available():
        output_lines.append("- Warning: ffmpeg unavailable; video output was not created")
    elif args.video and args.video_words_per_short is not None and not video_assets.get("videos"):
        output_lines.append("- Warning: no short videos were created")

    tts_status = "WARN" if tts_result.errors else "OK"
    tts_lines = [
        f"TTS status: {tts_status}",
        f"- Provider: {args.tts_provider}",
        f"- Example style: {args.example_style}",
        f"- Word repetition count: {args.word_repetition}",
        f"- Video words per short: {args.video_words_per_short or 'long video'}",
        f"- Generated: {len(tts_result.generated)}",
        f"- Skipped: {tts_result.skipped}",
    ]
    tts_lines.extend(f"- Error: {error}" for error in tts_result.errors)

    report_text = _append_sections(report_text, "Outputs", output_lines)
    report_text = _append_sections(report_text, "TTS", tts_lines)
    _write_report(args.out, report_text)
    return 0


def _load_source_or_write_report(source_path: Path, out_dir: Path) -> dict | None:
    try:
        return load_source(source_path)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        report = ValidationReport()
        report.add_error("source", f"Source load error: {error}")
        _write_report(out_dir, render_validation_report(report))
        return None


def _write_report(out_dir: Path, content: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "validation_report.md"
    output.write_text(content + "\n", encoding="utf-8")
    return output


def _append_sections(report: str, title: str, lines: list[str]) -> str:
    return "\n".join([report.rstrip(), "", f"## {title}", *lines])


if __name__ == "__main__":
    raise SystemExit(main())
