# JLPT Study Pipeline

A Codex skill and Python pipeline for generating JLPT study packages: Obsidian Markdown, Anki cards, subtitles, edge-tts audio, and optional MP4 videos.

## Setup

```bash
cd jlpt-study-pipeline
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Install `ffmpeg` separately if MP4 output is needed.

## edge-tts

edge-tts is the default TTS provider. It does not require an API key or project-specific endpoint configuration. It does require the `edge-tts` command from the Python package and network access to the Microsoft Edge TTS service.

The default voice is `ja-JP-NanamiNeural`. Override it with `--voice` if needed.

List available voices:

```bash
edge-tts --list-voices
```

Project reference: https://github.com/rany2/edge-tts

## Commands

Validate a source file:

```bash
python scripts/jlpt_pipeline.py validate --source examples/source.sample.json --out out/sample
```

Estimate TTS usage:

```bash
python scripts/jlpt_pipeline.py dry-run --source examples/source.sample.json --out out/sample
```

Build all outputs with edge-tts:

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

## Outputs

- Obsidian Markdown note.
- Anki `.apkg`.
- `anki.csv` fallback.
- `narration.txt`.
- `subtitles.ass`.
- `audio/` when TTS succeeds.
- `video.mp4` when `ffmpeg` is available and succeeds.
- `validation_report.md`.

## Source Data

The pipeline expects a `source.json` file with `metadata` and `entries`. AI-generated entries should use `verification_status: needs_review` until checked against trusted material.

## Install as an Agent Skill

Install the current project copy as an agent skill after local verification. It supports both Codex and Antigravity CLI.

Target paths by default (`--tool all`):
- **Codex**: Repo-level targets `.codex/skills/jlpt-study-pipeline`; user-level targets `$CODEX_HOME/skills/jlpt-study-pipeline` or `~/.codex/skills/jlpt-study-pipeline`.
- **Antigravity CLI**: Repo-level targets `.agents/skills/jlpt-study-pipeline`; user-level/shared targets `$GEMINI_HOME/skills/jlpt-study-pipeline` or `~/.gemini/skills/jlpt-study-pipeline`.

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

Use `--repo-root`, `--codex-home`, `--gemini-home`, or `--target` for explicit destinations. Generated outputs, virtualenvs, caches, and `.git` are excluded from installs.
