# Video Field Configuration & Text Wrapping — Design Spec

**Date:** 2026-06-22  
**Status:** Approved

---

## Overview

Two features are added to the JLPT study video pipeline:

1. **Field display configuration** — users interactively choose how many times each subtitle field plays in the video (0 = hidden) and the display order, via CLI dialogue and `jlpt_pipeline.py` args.
2. **Automatic text wrapping** — long subtitle lines wrap to the next line rather than overflowing the screen, for both landscape (1920×1080) and portrait (1080×1920) formats.

---

## Feature 1: Field Display Configuration

### Configurable Fields

| Field | Kind key | Default count | Default order | Audio |
|-------|----------|---------------|---------------|-------|
| 日文字彙 | `term` | 2 | 1 | Japanese voice, repeated `count` times |
| 字彙翻譯 | `zh_tw_meaning` | 1 | 2 | Chinese voice, repeated `count` times |
| 日文例句/短句 | `example_ja` | 1 | 3 | Japanese voice, repeated `count` times |
| 例句翻譯（嵌入） | `show_example_translation` | `True` | — | No audio (inline text only) |

**Behaviour rules:**
- `count = 0` → field not shown, no audio generated or played.
- `count = N > 0` → field shows as one subtitle card; audio plays N times before advancing (same as current `word_repetition` for term).
- `show_example_translation` only has effect when `example_ja` count > 0; the Chinese translation is appended inline to the example card.
- `order` values must be distinct integers ≥ 1; fields are sorted ascending before rendering.

### `VideoFieldConfig` Dataclass (models.py)

```python
@dataclass
class VideoFieldConfig:
    term_count: int = 2
    meaning_count: int = 1
    example_count: int = 1
    show_example_translation: bool = True
    term_order: int = 1
    meaning_order: int = 2
    example_order: int = 3

    def ordered_fields(self) -> list[tuple[str, int]]:
        """Return (kind, count) pairs sorted by order, excluding count=0 fields."""
        candidates = [
            ("term", self.term_count, self.term_order),
            ("zh_tw_meaning", self.meaning_count, self.meaning_order),
            ("example_ja", self.example_count, self.example_order),
        ]
        return [
            (kind, count)
            for kind, count, _ in sorted(candidates, key=lambda x: x[2])
            if count > 0
        ]
```

`word_repetition` is removed everywhere; `VideoFieldConfig` is the single source of truth.

### TTS Changes (tts.py)

`tts_items` accepts `VideoFieldConfig` instead of `word_repetition: int`.

Audio is generated per `(entry_id, kind)`:
- `term` → `config.term_count` TTS items (same text/voice repeated; same hash → same cached file reused)
- `zh_tw_meaning` → `config.meaning_count` items (skipped if 0)
- `example_ja` → `config.example_count` items (skipped if 0)
- `example_zh_tw` → never in TTS

`audio_paths_for_source` return type changes from `list[Path]` to:

```python
dict[tuple[str, str], list[Path]]
# key: (entry_id, kind)
# value: list of paths, length == count for that field
```

This breaks the positional dependency, allowing `timeline_items` to consume audio in any configured order.

### Video Changes (video.py)

`timeline_items` signature:

```python
def timeline_items(
    source: dict,
    audio_dict: dict[tuple[str, str], list[Path]] | None = None,
    example_style: str = EXAMPLE_STYLE_SENTENCE,
    field_config: VideoFieldConfig | None = None,
) -> list[dict]:
```

For each entry, iterates `field_config.ordered_fields()`. Looks up audio via `audio_dict.get((entry_id, kind), [])`. The term field spans all N audio plays as a single visual card (one timeline item covering total duration of N clips).

### Interactive Dialogue (build_youtube_jlpt.py)

New function `ask_video_field_config() -> VideoFieldConfig | None`:
- Only runs when `sys.stdin.isatty()`.
- Returns `None` (use defaults) if user presses Enter on every prompt.
- Validates order uniqueness; re-prompts on invalid input.

```
=== Video Field Configuration ===
設定各欄位在影片中出現的次數（0 = 不顯示，直接 Enter = 使用預設值）

日文字彙播放次數 [預設: 2]:
字彙翻譯播放次數 [預設: 1]:
日文例句播放次數 [預設: 1]:
是否嵌入例句翻譯？[Y/n]:

設定顯示順序（1 = 最先，輸入 1~3 不重複的數字）
日文字彙順序 [預設: 1]:
字彙翻譯順序 [預設: 2]:
日文例句順序 [預設: 3]:
```

### CLI Parameters (jlpt_pipeline.py)

Added to `build`, `dry-run`, and `validate` subcommands:

| Parameter | Default | Notes |
|-----------|---------|-------|
| `--term-count N` | 2 | Replaces `--word-repetition` |
| `--meaning-count N` | 1 | |
| `--example-count N` | 1 | |
| `--show-example-translation` / `--no-show-example-translation` | enabled | |
| `--term-order N` | 1 | |
| `--meaning-order N` | 2 | |
| `--example-order N` | 3 | |
| `--shorts-portrait` | enabled | Short videos use 1080×1920; see Feature 2 |

`--word-repetition` is removed.

---

## Feature 2: Automatic Text Wrapping

### Problem

Long Japanese example sentences and Chinese translations overflow the video frame width in the current ASS subtitle output (`WrapStyle: 0` with no manual line breaks).

### Solution

Pre-process subtitle text with `wrap_text(text: str, max_em: float) -> str` before `escape_ass()` is applied. Inserts `\n` characters at wrap points; `escape_ass` converts them to ASS hard newlines (`\N`).

**Character width estimation:**
- CJK characters (U+3000–U+9FFF and CJK punctuation): 1.0 em (full-width)
- ASCII, digits, basic punctuation: 0.5 em (half-width)

Wrap at the character boundary where accumulated em-width exceeds `max_em`. No space-boundary requirement (Japanese has none).

### Resolution-Aware Parameters

The ASS template `video_scene.ass.j2` is parameterized to accept `play_res_x`, `play_res_y`, font sizes, and margins as Jinja variables instead of hard-coded values.

| Format | PlayResX | PlayResY | Term font | Term margin | Body font | Body margin |
|--------|----------|----------|-----------|-------------|-----------|-------------|
| Landscape 1920×1080 | 1920 | 1080 | 128 | 120 | 76 | 150 |
| Portrait 1080×1920 | 1080 | 1920 | 80 | 60 | 52 | 40 |

Derived `max_em` per style:

| Format | Term max_em | Body max_em |
|--------|-------------|-------------|
| Landscape | ~13 | ~21 |
| Portrait | ~12 | ~19 |

### Portrait Video Generation

`write_video` gains a `portrait: bool = False` parameter:
- `portrait=True` → ffmpeg uses `s=1080x1920`, ASS template receives portrait parameters.
- `write_short_videos` passes `portrait=True` when `--shorts-portrait` is set (default enabled).
- Regular (long) video always uses landscape.

---

## Affected Files

| File | Change |
|------|--------|
| `scripts/jlpt_pipeline/models.py` | Add `VideoFieldConfig` dataclass |
| `scripts/jlpt_pipeline/tts.py` | Accept `VideoFieldConfig`; return audio dict |
| `scripts/jlpt_pipeline/video.py` | Dict-based audio lookup; `wrap_text()`; `portrait` flag |
| `templates/video_scene.ass.j2` | Parameterize resolution, font sizes, margins |
| `scripts/jlpt_pipeline/cli.py` | Replace `--word-repetition` with 7 new params; build `VideoFieldConfig` |
| `scripts/build_youtube_jlpt.py` | Add `ask_video_field_config()` dialogue |
| `tests/test_tts.py` | Update for new signatures |
| `tests/test_video_assets.py` | Update for new signatures + portrait mode |
| `tests/test_cli.py` | Update for removed/added CLI args |

**Not affected:** Anki export, Obsidian export, validation logic, TTS cache files.
