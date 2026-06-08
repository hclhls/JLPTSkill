import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "source.sample.json"
sys.path.insert(0, str(ROOT / "scripts"))

from jlpt_pipeline.tts import estimate_tts_chars, synthesize_entries
from jlpt_pipeline.validation import load_source


def test_estimate_tts_chars_skips_rejected_entries():
    source = load_source(SAMPLE)

    estimate = estimate_tts_chars(source)

    assert estimate.total_chars > 0
    assert estimate.items
    assert "ざあざあ" not in [item.text for item in estimate.items]


def test_synthesize_entries_none_provider_creates_audio_and_skips_items(tmp_path):
    source = load_source(SAMPLE)

    result = synthesize_entries(source, tmp_path, provider="none")

    assert (tmp_path / "audio").is_dir()
    assert result.generated == []
    assert result.skipped == 4
    assert result.errors == []
    assert list((tmp_path / "audio").iterdir()) == []


def test_synthesize_entries_max_chars_error_generates_nothing(tmp_path):
    source = load_source(SAMPLE)

    result = synthesize_entries(source, tmp_path, provider="none", max_chars=1)

    assert result.generated == []
    assert result.skipped == 0
    assert any("max tts chars" in error for error in result.errors)
    assert list((tmp_path / "audio").iterdir()) == []
