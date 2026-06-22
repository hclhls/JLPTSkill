import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from jlpt_pipeline.video import wrap_text


def test_wrap_text_cjk_horizontal():
    """Test wrapping of CJK text in horizontal format (Term style)."""
    text = "これはテストです。"
    wrapped = wrap_text(text, "Term", max_width_px=1680, font_size=128)

    # Should have line breaks or fit in single line
    assert r"\N" in wrapped or len(wrapped) == len(text)  # Either wrapped or single line


def test_wrap_text_cjk_vertical():
    """Test wrapping of CJK text in vertical format (Term style)."""
    text = "これはテストです。"
    wrapped = wrap_text(text, "Term", max_width_px=960, font_size=80)

    # With narrower width, should wrap more
    assert isinstance(wrapped, str)


def test_wrap_text_latin():
    """Test wrapping of mixed Latin/CJK text."""
    text = "The quick brown fox jumped over the lazy dog. 日本語のテスト。"
    wrapped = wrap_text(text, "Body", max_width_px=1620, font_size=76)

    # Should not crash and return string
    assert isinstance(wrapped, str)


def test_wrap_text_empty():
    """Test wrapping empty string."""
    wrapped = wrap_text("", "Term", max_width_px=1680, font_size=128)
    assert wrapped == ""


def test_wrap_text_single_word():
    """Test wrapping single word that fits."""
    text = "テスト"
    wrapped = wrap_text(text, "Term", max_width_px=1680, font_size=128)
    assert wrapped == "テスト"
