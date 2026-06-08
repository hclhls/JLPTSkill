from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .anki import write_anki_csv, write_anki_package
from .obsidian import write_obsidian_markdown
from .tts import DEFAULT_VOICE, estimate_tts_chars, synthesize_entries
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
    validate.set_defaults(command=_validate_command)

    dry_run = subcommands.add_parser("dry-run")
    _add_source_out_args(dry_run)
    dry_run.set_defaults(command=_dry_run_command)

    build = subcommands.add_parser("build")
    _add_source_out_args(build)
    build.add_argument("--deck-name", required=True)
    build.add_argument(
        "--tts-provider",
        default="azure",
        choices=["azure", "openai", "none"],
    )
    build.add_argument("--voice", default=DEFAULT_VOICE)
    build.add_argument("--slug", default="jlpt-study")
    build.add_argument("--video", action="store_true")
    build.add_argument("--max-tts-chars", type=int)
    build.add_argument("--no-tts-cache", action="store_true")
    build.set_defaults(command=_build_command)

    return parser


def _add_source_out_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)


def _validate_command(args: argparse.Namespace) -> int:
    source = load_source(args.source)
    report = validate_source(source)
    _write_report(args.out, render_validation_report(report))
    return 0 if report.ok else 1


def _dry_run_command(args: argparse.Namespace) -> int:
    source = load_source(args.source)
    report = validate_source(source)
    if not report.ok:
        _write_report(args.out, render_validation_report(report))
        return 1

    estimate = estimate_tts_chars(source)
    report_text = _append_sections(
        render_validation_report(report),
        "Dry Run",
        [f"Estimated TTS characters: {estimate.total_chars}"],
    )
    _write_report(args.out, report_text)
    return 0 if report.ok else 1


def _build_command(args: argparse.Namespace) -> int:
    source = load_source(args.source)
    report = validate_source(source)
    report_text = render_validation_report(report)
    if not report.ok:
        _write_report(args.out, report_text)
        return 1

    obsidian = write_obsidian_markdown(source, args.out, args.slug)
    anki_csv = write_anki_csv(source, args.out)
    anki_package = write_anki_package(source, args.out, args.deck_name)
    video_assets = build_video_assets(source, args.out, make_video=args.video)
    tts_result = synthesize_entries(
        source,
        args.out,
        provider=args.tts_provider,
        voice=args.voice,
        max_chars=args.max_tts_chars,
        use_cache=not args.no_tts_cache,
    )

    output_lines = [
        f"- Obsidian markdown: {obsidian.name}",
        f"- Anki CSV: {anki_csv.name}",
        f"- Anki package: {anki_package.name}",
        f"- Narration: {video_assets['narration'].name}",
        f"- Subtitles: {video_assets['subtitles'].name}",
    ]
    if video_assets["video"] is not None:
        output_lines.append(f"- Video: {video_assets['video'].name}")
    elif args.video and not ffmpeg_available():
        output_lines.append("- Warning: ffmpeg unavailable; video.mp4 was not created")

    tts_lines = [
        f"- Provider: {args.tts_provider}",
        f"- Generated: {len(tts_result.generated)}",
        f"- Skipped: {tts_result.skipped}",
    ]
    tts_lines.extend(f"- Error: {error}" for error in tts_result.errors)

    report_text = _append_sections(report_text, "Outputs", output_lines)
    report_text = _append_sections(report_text, "TTS", tts_lines)
    _write_report(args.out, report_text)
    return 0


def _write_report(out_dir: Path, content: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "validation_report.md"
    output.write_text(content + "\n", encoding="utf-8")
    return output


def _append_sections(report: str, title: str, lines: list[str]) -> str:
    return "\n".join([report.rstrip(), "", f"## {title}", *lines])


if __name__ == "__main__":
    raise SystemExit(main())
