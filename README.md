# JLPT Study Pipeline

A local Python pipeline and agent skill for generating Japanese JLPT study packages from structured source data. It can produce Obsidian notes, bidirectional Anki cards, subtitle files, narration scripts, edge-tts audio, and optional MP4 study videos.

The main project lives in [`jlpt-study-pipeline/`](jlpt-study-pipeline/).

## What It Does

- Validates JLPT study source data before export.
- Generates Obsidian Markdown notes for review and knowledge-base use.
- Builds bidirectional Anki decks and CSV fallback exports.
- Creates narration text and ASS subtitles for study videos.
- Uses `edge-tts` for Japanese text-to-speech without project-specific API keys.
- Optionally assembles MP4 videos when `ffmpeg` is installed.
- Provides install scripts for using the pipeline as a Codex or Antigravity CLI agent skill.

## Repository Layout

```text
.
|-- jlpt-study-pipeline/       # Python CLI, skill files, templates, examples, and tests
|-- docs/superpowers/          # Design and implementation planning notes
`-- sources/                   # Local source material, ignored by Git
```

Generated outputs, virtual environments, local agent-skill installs, caches, and media files are ignored by Git.

## Requirements

- Python 3.11 or newer is recommended.
- `ffmpeg` is required only for MP4 output.
- Network access is required when using `edge-tts`.
- `youtube-transcript-api` is optional and only needed for the YouTube helper script.

## Quick Start

```bash
cd jlpt-study-pipeline
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Validate the sample source file:

```bash
python scripts/jlpt_pipeline.py validate \
  --source examples/source.sample.json \
  --out out/sample
```

Build a full study package with audio and video:

```bash
python scripts/jlpt_pipeline.py build \
  --source examples/source.sample.json \
  --out out/sample \
  --deck-name "Sample JLPT" \
  --tts-provider edge \
  --voice ja-JP-NanamiNeural \
  --slug sample \
  --video
```

Build without text-to-speech:

```bash
python scripts/jlpt_pipeline.py build \
  --source examples/source.sample.json \
  --out out/sample \
  --deck-name "Sample JLPT" \
  --tts-provider none \
  --slug sample \
  --video
```

## Source Data

The pipeline expects a `source.json` file with `metadata` and `entries`. AI-generated entries should use `verification_status: needs_review` until checked against trusted learning material. JLPT levels should be treated as estimates unless they come from verified sources.

See [`jlpt-study-pipeline/examples/source.sample.json`](jlpt-study-pipeline/examples/source.sample.json) for the expected shape.

## Outputs

A successful build can create:

- Obsidian Markdown note.
- Anki `.apkg` deck.
- `anki.csv` fallback export.
- `narration.txt`.
- `subtitles.ass`.
- `audio/` files when text-to-speech succeeds.
- `video.mp4` when `ffmpeg` is available and video generation succeeds.
- `validation_report.md`.

## YouTube Transcript Helper

[`jlpt-study-pipeline/scripts/build_youtube_jlpt.py`](jlpt-study-pipeline/scripts/build_youtube_jlpt.py) can fetch a YouTube transcript, save raw transcript text, prompt for JLPT vocabulary extraction, and then run the normal build once `source.json` exists.

Install the optional dependency first:

```bash
pip install youtube-transcript-api
```

Example:

```bash
python scripts/build_youtube_jlpt.py \
  --url "https://www.youtube.com/watch?v=VIDEO_ID" \
  --deck-name "YouTube JLPT Study" \
  --video
```

## Agent Skill Installation

The project can be installed as an agent skill for Codex or Antigravity CLI after local verification.

Preview install targets:

```bash
cd jlpt-study-pipeline
python3 scripts/skill_install.py --level repo --dry-run
python3 scripts/skill_install.py --level user --dry-run
```

Install or update:

```bash
python3 scripts/skill_install.py --level repo --force
python3 scripts/skill_install.py --level user --force
```

Uninstall:

```bash
python3 scripts/skill_uninstall.py --level repo --yes --missing-ok
python3 scripts/skill_uninstall.py --level user --yes --missing-ok
```

Use `--tool codex` or `--tool antigravity` to restrict installation to one tool.

## Development

Run the test suite from the project directory:

```bash
cd jlpt-study-pipeline
python -m pytest
```

Before pushing, check that only source files and documentation are tracked:

```bash
git status --short --ignored
git diff --check
```
