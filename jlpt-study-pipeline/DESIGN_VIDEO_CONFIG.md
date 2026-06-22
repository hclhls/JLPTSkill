# Video Field Configuration Design

## Overview

This document describes the implementation of configurable video field repetition counts,
display orders, and text wrapping for JLPT study videos.

## Architecture

### VideoFieldConfig Dataclass (models.py)

Centralizes all video field configuration in a single immutable dataclass:

- `term_count`: How many times to repeat the vocabulary/term audio (default: 2)
- `meaning_count`: How many times to repeat the translation/meaning audio (default: 1)
- `example_count`: How many times to repeat the example sentence audio (default: 1)
- `show_example_translation`: Whether to display example translations (default: True)
- `term_order`, `meaning_order`, `example_order`: Display order (1-3, default: 1, 2, 3)

Method `ordered_fields()` returns fields sorted by their order values.

### TTS Layer Updates (tts.py)

- `tts_items()` now accepts `VideoFieldConfig` instead of `word_repetition` int
- `audio_paths_for_source()` returns `dict[(entry_id, kind), list[Path]]` instead of flat list
  - This decouples audio file order from their cache position
  - Supports arbitrary repetition and reordering

### Text Wrapping (video.py)

New `wrap_text()` function:
- Wraps CJK text at character boundaries
- Wraps Latin text at word boundaries
- Inserts ASS newline markers (`\N`) at break points
- Considers font size and max width to estimate line length

### Video Generation (video.py)

Updated `write_video()`:
- Accepts `VideoFieldConfig` to control field repetition and order
- Accepts `portrait` flag for 1080×1920 vertical format (e.g., YouTube Shorts)
- Uses `wrap_text()` to wrap display text
- Parameterizes ASS template with resolution and font sizes

### ASS Template (templates/video_scene.ass.j2)

Parameterized template:
- `play_res_x`, `play_res_y`: Video resolution
- `term_font_size`, `body_font_size`: Font sizes based on format

### CLI Updates (cli.py)

New arguments for `jlpt-pipeline build`:
- `--term-count N` (default: 2, replaces `--word-repetition`)
- `--meaning-count N` (default: 1)
- `--example-count N` (default: 1)
- `--show-example-translation / --no-show-example-translation` (default: True)
- `--term-order N` (default: 1)
- `--meaning-order N` (default: 2)
- `--example-order N` (default: 3)
- `--shorts-portrait` (enable vertical format)

### Interactive Configuration (build_youtube_jlpt.py)

New `ask_video_field_config()` function:
- When stdin is a TTY, prompts user for configuration
- Returns `VideoFieldConfig` or None (use defaults)
- Used in `build_youtube_jlpt.py`'s interactive flow

## Format Support

### Horizontal (1920×1080)
- Term font: 128px, max width: 1680px (~13 CJK chars/line)
- Body font: 76px, max width: 1620px (~21 CJK chars/line)

### Vertical (1080×1920)
- Term font: 80px, max width: 960px (~12 CJK chars/line)
- Body font: 52px, max width: 1000px (~19 CJK chars/line)

## Testing

All public functions have unit tests:
- `VideoFieldConfig` construction and `ordered_fields()`
- `tts_items()` with various configs
- `audio_paths_for_source()` dict output
- `wrap_text()` with CJK, Latin, and mixed text
- `write_video()` in horizontal and portrait modes
- CLI argument parsing
- Integration tests end-to-end

## Migration

Legacy `--word-repetition` parameter removed. Users should use `--term-count` instead.
Default values are identical to ensure no breaking changes to output.

## Examples

### CLI

```bash
# Repeat term 3 times, meaning 2 times
jlpt-pipeline build --source data.json --out video/ --deck-name Study \
  --term-count 3 --meaning-count 2

# Change display order: meaning first, then term, then example
jlpt-pipeline build --source data.json --out video/ --deck-name Study \
  --meaning-order 1 --term-order 2 --example-order 3

# Create vertical YouTube Shorts
jlpt-pipeline build --source data.json --out video/ --deck-name Study \
  --shorts-portrait --video
```

### Programmatic

```python
from jlpt_pipeline.models import VideoFieldConfig
from jlpt_pipeline.tts import audio_paths_for_source
from jlpt_pipeline.video import write_video

config = VideoFieldConfig(
    term_count=2,
    meaning_count=1,
    example_count=1,
)

audio_dict = audio_paths_for_source(source, out_dir, config=config)
write_video(source, out_dir, audio_dict, config, portrait=True)
```
