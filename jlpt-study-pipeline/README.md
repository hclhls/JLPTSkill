# JLPT Study Pipeline

A Codex skill and Python pipeline for generating JLPT study packages: Obsidian Markdown, Anki cards, subtitles, Azure Speech TTS audio, and optional MP4 videos.

## Setup

```bash
cd jlpt-study-pipeline
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Install `ffmpeg` separately if MP4 output is needed.

## Azure Speech

Azure Speech is the default TTS provider. Set these environment variables:

```bash
export AZURE_SPEECH_KEY="..."
export AZURE_SPEECH_REGION="..."
```

The default voice is `ja-JP-NanamiNeural`. Override it with `--voice` if the voice is unavailable in your Azure region.

Check official Microsoft pricing and quota pages before large generation:

- https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-services-quotas-and-limits
- https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/

## Commands

Validate a source file:

```bash
python scripts/jlpt_pipeline.py validate --source examples/source.sample.json --out out/sample
```

Estimate TTS usage:

```bash
python scripts/jlpt_pipeline.py dry-run --source examples/source.sample.json --out out/sample
```

Build all outputs with Azure Speech:

```bash
python scripts/jlpt_pipeline.py build \
  --source examples/source.sample.json \
  --out out/sample \
  --deck-name "Sample JLPT" \
  --tts-provider azure \
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

## Install as a Codex Skill

After local verification, install the skill into your personal Codex skill directory:

```bash
mkdir -p "$CODEX_HOME/skills"
cp -R jlpt-study-pipeline "$CODEX_HOME/skills/jlpt-study-pipeline"
```

Do this only after reviewing the local project output. If `CODEX_HOME` is unset, use your Codex home directory and keep the final path as `skills/jlpt-study-pipeline`.
