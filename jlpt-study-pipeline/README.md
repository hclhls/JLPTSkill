# JLPT Study Pipeline Usage Guide

This directory contains the runnable Python CLI, templates, tests, examples, and agent skill files for the JLPT Study Pipeline.

For the repository overview, start with the [root README](../README.md).

## Purpose

The pipeline turns validated JLPT study source data into repeatable learning assets:

- Obsidian Markdown notes.
- Bidirectional Anki `.apkg` decks.
- `anki.csv` fallback exports.
- Narration scripts and ASS subtitle files.
- Optional `edge-tts` audio.
- Optional MP4 study videos through `ffmpeg`.

## Setup

Create and activate a virtual environment from this directory:

```bash
cd jlpt-study-pipeline
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Install `ffmpeg` separately if MP4 output is needed.

## Text-to-Speech

`edge-tts` is the default TTS provider. It does not require an API key or project-specific endpoint configuration, but it does require the `edge-tts` command from the Python package and network access to the Microsoft Edge TTS service.

The default Japanese voice is `ja-JP-NanamiNeural`. Override it with `--voice` if needed.

List available voices:

```bash
edge-tts --list-voices
```

Project reference: https://github.com/rany2/edge-tts

## Source Data

The CLI expects a `source.json` file with `metadata` and `entries`. See [`examples/source.sample.json`](examples/source.sample.json) for the schema shape used by tests and sample builds.

Guidelines:

- Use `verification_status: needs_review` for AI-generated entries until they are checked against trusted material.
- Treat JLPT levels as estimates unless they come from verified sources.
- Use `verification_status: rejected` for entries that should remain auditable in Markdown but be skipped by Anki, TTS, and video generation.

## Commands

Validate a source file:

```bash
python scripts/jlpt_pipeline.py validate \
  --source examples/source.sample.json \
  --out out/sample
```

Estimate TTS usage without generating audio:

```bash
python scripts/jlpt_pipeline.py dry-run \
  --source examples/source.sample.json \
  --out out/sample
```

Build all outputs with `edge-tts`:

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

Build without TTS:

```bash
python scripts/jlpt_pipeline.py build \
  --source examples/source.sample.json \
  --out out/sample \
  --deck-name "Sample JLPT" \
  --tts-provider none \
  --slug sample \
  --video
```

## YouTube Transcript Helper

`scripts/build_youtube_jlpt.py` can fetch a YouTube transcript, save transcript text, prompt for JLPT vocabulary extraction, and then run the standard build once `source.json` exists in the output directory.

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

The helper creates `out/<video_id>/transcript_raw.txt` by default. If `out/<video_id>/source.json` does not exist yet, it prints a prompt for generating that source file and exits. Run the helper again after creating `source.json`.

## Outputs

A successful build can create:

- Obsidian Markdown note.
- Anki `.apkg` deck.
- `anki.csv` fallback export.
- `narration.txt`.
- `subtitles.ass`.
- `audio/` when TTS succeeds.
- `video.mp4` when `ffmpeg` is available and succeeds.
- `validation_report.md`.

Generated files are written under the selected `--out` directory and are ignored by Git.

## Install as an Agent Skill

Install the current project copy as an agent skill after local verification. The installer supports both Codex and Antigravity CLI.

Default targets for `--tool all`:

- Codex repo-level: `.codex/skills/jlpt-study-pipeline`.
- Codex user-level: `$CODEX_HOME/skills/jlpt-study-pipeline` or `~/.codex/skills/jlpt-study-pipeline`.
- Antigravity CLI repo-level: `.agents/skills/jlpt-study-pipeline`.
- Antigravity CLI user-level/shared: `$GEMINI_HOME/skills/jlpt-study-pipeline` or `~/.gemini/skills/jlpt-study-pipeline`.

Use `--tool codex` or `--tool antigravity` to restrict the installation to a single tool.

Preview targets:

```bash
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

Use `--repo-root`, `--codex-home`, `--gemini-home`, or `--target` for explicit destinations. Generated outputs, virtual environments, caches, and `.git` are excluded from installs.

## Development

Run tests from this directory:

```bash
python -m pytest
```

Before committing documentation or code changes:

```bash
git diff --check
python -m pytest
```
