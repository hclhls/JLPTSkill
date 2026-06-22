#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from jlpt_pipeline.models import VideoFieldConfig

def get_video_id(url_or_id: str) -> str:
    if "youtube.com" in url_or_id or "youtu.be" in url_or_id:
        # Simple extraction
        if "v=" in url_or_id:
            return url_or_id.split("v=")[1].split("&")[0]
        elif "youtu.be/" in url_or_id:
            return url_or_id.split("youtu.be/")[1].split("?")[0]
    return url_or_id

def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def ask_video_words_per_short() -> int | None:
    if not sys.stdin.isatty():
        return None

    print("\n=== Video Length ===")
    print("Press Enter to generate one long video with all vocabulary.")
    while True:
        answer = input("Words per YouTube short video? ").strip()
        if answer == "":
            return None
        try:
            value = int(answer)
        except ValueError:
            print("Please enter a positive integer, or press Enter for one long video.")
            continue
        if value >= 1:
            return value
        print("Please enter a value of 1 or greater.")

def ask_video_field_config() -> VideoFieldConfig | None:
    """Ask user for video field configuration if TTY.

    Returns VideoFieldConfig if TTY and user confirms, else None (use defaults).
    """
    if not sys.stdin.isatty():
        return None

    print("\n=== Video Field Configuration ===")
    print("Configure how many times each field appears in the video audio.")
    print("(Press Enter to use default values)\n")

    # Collect counts
    term_count_input = input("Term repetition count [default: 2]: ").strip()
    term_count = int(term_count_input) if term_count_input else 2

    meaning_count_input = input("Meaning repetition count [default: 1]: ").strip()
    meaning_count = int(meaning_count_input) if meaning_count_input else 1

    example_count_input = input("Example repetition count [default: 1]: ").strip()
    example_count = int(example_count_input) if example_count_input else 1

    show_translation_input = input("Show example translation? [Y/n]: ").strip().lower()
    show_example_translation = show_translation_input != "n"

    print("\nConfigure display order (1=first, 2=second, 3=third):")
    term_order_input = input("Term order [default: 1]: ").strip()
    term_order = int(term_order_input) if term_order_input else 1

    meaning_order_input = input("Meaning order [default: 2]: ").strip()
    meaning_order = int(meaning_order_input) if meaning_order_input else 2

    example_order_input = input("Example order [default: 3]: ").strip()
    example_order = int(example_order_input) if example_order_input else 3

    return VideoFieldConfig(
        term_count=term_count,
        meaning_count=meaning_count,
        example_count=example_count,
        show_example_translation=show_example_translation,
        term_order=term_order,
        meaning_order=meaning_order,
        example_order=example_order,
    )

def main() -> int:
    parser = argparse.ArgumentParser(description="Automate the JLPT study pipeline for a YouTube video.")
    parser.add_argument("--url", required=True, help="YouTube Video URL or ID")
    parser.add_argument("--out", help="Output directory (default: out/<video_id>)")
    parser.add_argument("--deck-name", default="YouTube JLPT Study", help="Anki deck name")
    parser.add_argument("--voice", default="ja-JP-NanamiNeural", help="TTS Voice")
    parser.add_argument("--video", action="store_true", help="Build MP4 video output")
    parser.add_argument(
        "--video-words-per-short",
        type=positive_int,
        help="Create YouTube short-style segmented videos with this many words per video. Omit for an interactive prompt when possible.",
    )
    args = parser.parse_args()

    video_id = get_video_id(args.url)
    if not video_id:
        print("Error: Could not parse YouTube video ID.", file=sys.stderr)
        return 1

    out_dir = Path(args.out) if args.out else Path(f"out/{video_id}")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Step 1: Fetching YouTube transcript for {video_id} ===")
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)

        try:
            transcript = transcript_list.find_transcript(['ja'])
            raw_data = transcript.fetch()
        except Exception:
            # Fallback to translate
            first_transcript = next(iter(transcript_list))
            if first_transcript.language_code != 'ja':
                raw_data = first_transcript.translate('ja').fetch()
            else:
                raw_data = first_transcript.fetch()

        # Save transcript text
        text_lines = [item['text'] for item in raw_data if item['text'] and not item['text'].startswith('[')]
        combined_text = " ".join(text_lines)
        transcript_path = out_dir / "transcript_raw.txt"
        transcript_path.write_text(combined_text, encoding="utf-8")
        print(f"Saved transcript text to: {transcript_path}")
    except Exception as e:
        print(f"Error fetching transcript: {e}", file=sys.stderr)
        return 1

    # Check if source.json already exists
    source_json_path = out_dir / "source.json"
    if not source_json_path.exists():
        print("\n=== Step 2: Extract N1/N2 Vocabulary ===")
        print(f"To compile the JLPT pipeline, you need to generate '{source_json_path.name}'.")
        print("Please copy the text in the transcript and paste it into the AI agent with the following prompt:\n")
        print("--------------------------------------------------------------------------------")
        print(f"Please analyze the following text from YouTube video {video_id} and extract around 10-15 vocabulary words equivalent to N1/N2 levels.")
        print(f"Generate a JSON conforming to the schema of source.json, and save it to the file path: {source_json_path.absolute()}")
        print("--------------------------------------------------------------------------------\n")
        print("Once the file is generated, run this script again to build the study package.")
        return 0

    print("\n=== Step 3: Cleaning up 0-byte cached files ===")
    audio_dir = out_dir / "audio"
    if audio_dir.exists():
        deleted_count = 0
        for f in audio_dir.glob("*.mp3"):
            if f.stat().st_size == 0:
                f.unlink()
                deleted_count += 1
        if deleted_count > 0:
            print(f"Deleted {deleted_count} 0-byte cache MP3 file(s).")

    video_words_per_short = args.video_words_per_short
    if args.video and video_words_per_short is None:
        video_words_per_short = ask_video_words_per_short()

    print("\n=== Step 4: Running Build Pipeline ===")
    # Add virtual environment bin to PATH so edge-tts can be executed
    venv_bin = Path(__file__).resolve().parents[1] / ".venv" / "bin"
    env = os.environ.copy()
    if venv_bin.exists():
        env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"

    cmd = [
        sys.executable, "scripts/jlpt_pipeline.py", "build",
        "--source", str(source_json_path),
        "--out", str(out_dir),
        "--deck-name", args.deck_name,
        "--tts-provider", "edge",
        "--voice", args.voice,
        "--slug", video_id
    ]
    if args.video:
        cmd.append("--video")
        if video_words_per_short is not None:
            cmd.extend(["--video-words-per-short", str(video_words_per_short)])

    print(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env)

    if result.returncode == 0:
        print("\n=== Success! ===")
        print(f"All files have been successfully generated in {out_dir}")
        print(f"- Obsidian Markdown: {out_dir}/{video_id}.md")
        print(f"- Anki Package: {out_dir}/{args.deck_name.lower().replace(' ', '-')}.apkg")
        if args.video and video_words_per_short is None:
            print(f"- Video: {out_dir}/video.mp4")
        elif args.video:
            print(f"- Short videos: {out_dir}/shorts/short_*/video.mp4")
    else:
        print(f"\nError: Pipeline build exited with code {result.returncode}", file=sys.stderr)
        return result.returncode

    return 0

if __name__ == "__main__":
    sys.exit(main())
