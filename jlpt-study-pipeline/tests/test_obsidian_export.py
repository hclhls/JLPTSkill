import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "source.sample.json"
sys.path.insert(0, str(ROOT / "scripts"))

from jlpt_pipeline.obsidian import render_obsidian_markdown, write_obsidian_markdown
from jlpt_pipeline.validation import load_source


def test_render_obsidian_markdown_contains_frontmatter_and_sections():
    source = load_source(SAMPLE)

    rendered = render_obsidian_markdown(source)

    assert rendered.startswith("---\n")
    assert "topic: JLPT N1/N2 擬聲詞" in rendered
    assert "## 校對狀態" in rendered
    assert "## 詞條總覽" in rendered
    assert "## 詳細詞條" in rendered


def test_render_obsidian_markdown_keeps_rejected_for_audit():
    source = load_source(SAMPLE)

    rendered = render_obsidian_markdown(source)

    assert "ono-003" in rendered
    assert "rejected" in rendered


def test_write_obsidian_markdown(tmp_path):
    source = load_source(SAMPLE)

    output = write_obsidian_markdown(source, tmp_path, "sample")

    assert output == tmp_path / "sample.md"
    assert output.exists()
    assert "しみじみ" in output.read_text(encoding="utf-8")
