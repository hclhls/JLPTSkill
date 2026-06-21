from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Any

import genanki
from jinja2 import Environment, FileSystemLoader

from .models import active_entries, resolve_example, EXAMPLE_STYLE_SENTENCE

MODEL_ID = 1762345101
DECK_ID_BASE = 1762345200


def _template_env() -> Environment:
    root = Path(__file__).resolve().parents[2] / "templates"
    return Environment(
        loader=FileSystemLoader(root),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "jlpt-study"


def _render(template_name: str, entry: dict[str, Any]) -> str:
    return _template_env().get_template(template_name).render(entry=entry)


def _entry_with_resolved_example(
    entry: dict[str, Any], example_style: str = EXAMPLE_STYLE_SENTENCE
) -> dict[str, Any]:
    """Return a copy of *entry* with ``example_ja_resolved`` injected.

    Templates use ``entry.example_ja_resolved`` instead of ``entry.example_ja``
    so they automatically reflect the active example style.
    """
    augmented = dict(entry)
    augmented["example_ja_resolved"] = resolve_example(entry, example_style)
    return augmented

def build_anki_notes(
    source: dict[str, Any], example_style: str = EXAMPLE_STYLE_SENTENCE
) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    for entry in active_entries(source):
        resolved_entry = _entry_with_resolved_example(entry, example_style)
        base_guid = f"jlpt-study:{entry['id']}"
        notes.append(
            {
                "guid": f"{base_guid}:ja_to_zh",
                "direction": "ja_to_zh",
                "front": _render("anki_front_ja.html.j2", resolved_entry),
                "back": _render("anki_back_ja.html.j2", resolved_entry),
                "tags": _tags(entry),
            }
        )
        notes.append(
            {
                "guid": f"{base_guid}:zh_to_ja",
                "direction": "zh_to_ja",
                "front": _render("anki_front_zh.html.j2", resolved_entry),
                "back": _render("anki_back_zh.html.j2", resolved_entry),
                "tags": _tags(entry),
            }
        )
    return notes


def _tags(entry: dict[str, Any]) -> str:
    return " ".join(
        [
            _tag("jlpt", "jlpt"),
            _tag(entry.get("jlpt_level_estimate"), "unknown"),
            _tag(entry.get("category"), "uncategorized"),
            _tag(entry.get("verification_status"), "unknown"),
        ]
    )


def _tag(value: Any, fallback: str) -> str:
    raw = str(value if value not in (None, "") else fallback).lower()
    normalized = raw.replace("/", "_")
    normalized = re.sub(r"[^\w-]+", "_", normalized, flags=re.UNICODE)
    normalized = re.sub(r"[_-]+", "_", normalized).strip("_-")
    return normalized or fallback


def write_anki_csv(
    source: dict[str, Any], out_dir: Path, example_style: str = EXAMPLE_STYLE_SENTENCE
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "anki.csv"
    fields = ["guid", "direction", "front", "back", "tags"]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(build_anki_notes(source, example_style))
    return output


def write_anki_package(
    source: dict[str, Any], out_dir: Path, deck_name: str, example_style: str = EXAMPLE_STYLE_SENTENCE
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    deck_id = DECK_ID_BASE + int(
        hashlib.sha1(deck_name.encode("utf-8")).hexdigest()[:6], 16
    )
    deck = genanki.Deck(deck_id, deck_name)
    model = genanki.Model(
        MODEL_ID,
        "JLPTStudyBidirectional",
        fields=[
            {"name": "Front"},
            {"name": "Back"},
            {"name": "Direction"},
        ],
        templates=[
            {
                "name": "Card",
                "qfmt": "{{Front}}",
                "afmt": "{{FrontSide}}<hr id=answer>{{Back}}",
            }
        ],
        css=".term{font-size:32px}.kana,.meta,.review{color:#666}.example-ja{margin-top:1em}",
    )
    for note_data in build_anki_notes(source, example_style):
        note = genanki.Note(
            model=model,
            fields=[note_data["front"], note_data["back"], note_data["direction"]],
            tags=note_data["tags"].split(),
            guid=note_data["guid"],
        )
        deck.add_note(note)
    output = out_dir / f"{slugify(deck_name)}.apkg"
    genanki.Package(deck).write_to_file(output)
    return output
