from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


def markdown_cell(value: Any) -> str:
    cell = " ".join(str(value).splitlines())
    return cell.replace("|", r"\|").strip()


def _template_env() -> Environment:
    root = Path(__file__).resolve().parents[2] / "templates"
    env = Environment(
        loader=FileSystemLoader(root),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["markdown_cell"] = markdown_cell
    return env


def render_obsidian_markdown(source: dict[str, Any]) -> str:
    entries = source["entries"]
    status_counts = Counter(entry.get("verification_status", "unknown") for entry in entries)
    for status in ["needs_review", "reviewed", "rejected"]:
        status_counts.setdefault(status, 0)

    template = _template_env().get_template("obsidian_note.md.j2")
    return template.render(
        metadata=source.get("metadata", {}),
        entries=entries,
        status_counts=dict(status_counts),
    )


def write_obsidian_markdown(source: dict[str, Any], out_dir: Path, slug: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{slug}.md"
    output.write_text(render_obsidian_markdown(source), encoding="utf-8")
    return output
