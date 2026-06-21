---
name: jlpt-study-pipeline
description: Generate JLPT study packages with Obsidian Markdown, Anki cards, edge-tts audio assets, and immersive video outputs from a user-provided Japanese study topic.
---

# JLPT Study Pipeline

Use this skill when the user asks to generate JLPT learning material, Japanese vocabulary packs, Obsidian notes, Anki cards, or immersive study videos.

## Required Inputs

If any required input is missing, ask for it before generating files:

- Topic, such as `JLPT N1/N2 擬聲詞 100 個`.
- Output directory.
- Target JLPT level or levels.
- Item count.

## Data Generation Rules

Generate `source.json` before running the pipeline. The JSON must contain `metadata` and `entries`.

Each entry must include:

- `id`
- `term`
- `kana`
- `jlpt_level_estimate`
- `category`
- `zh_tw_meaning`
- `example_ja` — complete Japanese sentence using the vocabulary
- `example_ja_phrase` *(optional)* — short phrase or collocation containing the vocabulary word, without forming a full sentence. Include this when a concise phrase is more useful for quick recall than a full sentence.
- `example_zh_tw`
- `recall_prompt_zh_tw`
- `verification_status`

Use Traditional Chinese for explanations. Use natural Japanese for examples. If the content is AI-generated and not checked against user-provided source material, set `verification_status` to `needs_review` and treat the JLPT level as an estimate.

Do not claim JLPT level authority unless the user provides verified source material. Include `exam_risk_note_zh_tw` when a level or usage point should be checked.

## Output Workflow

After `source.json` exists, run:

```bash
python scripts/jlpt_pipeline.py build \
  --source path/to/source.json \
  --out path/to/output \
  --deck-name "JLPT Study" \
  --tts-provider edge \
  --voice ja-JP-NanamiNeural \
  --example-style sentence \
  --word-repetition 2 \
  --video
```

Use `--example-style phrase` to use the short `example_ja_phrase` field instead of the full sentence for TTS audio, video subtitles, and Anki card backs. If an entry has no `example_ja_phrase`, it falls back to `example_ja` automatically. Use `--word-repetition <count>` to configure how many times the Japanese vocabulary word is read out (default: 2). **Always ask the user which style and word repetition count they prefer** before running the pipeline.

The pipeline exports Obsidian Markdown, Anki `.apkg`, `anki.csv`, `narration.txt`, `subtitles.ass`, optional edge-tts audio, optional `video.mp4`, and `validation_report.md`.

If edge-tts is unavailable or audio is not needed, use `--tts-provider none` so the user still gets Markdown, Anki, subtitles, narration, and silent video assets.

## edge-tts

edge-tts is the default TTS provider. It does not require an API key, but it does require the `edge-tts` command from the Python package and network access to the Microsoft Edge TTS service.

Use `dry-run` before large generations to estimate character usage:

```bash
python scripts/jlpt_pipeline.py dry-run --source path/to/source.json --out path/to/output
```

List available voices with:

```bash
edge-tts --list-voices
```

## Reporting

At the end, report generated file paths and summarize validation warnings. Treat `needs_review` as a normal review state, not as an error.
