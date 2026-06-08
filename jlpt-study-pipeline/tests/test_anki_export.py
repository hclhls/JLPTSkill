import csv
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "source.sample.json"
sys.path.insert(0, str(ROOT / "scripts"))

from jlpt_pipeline.anki import build_anki_notes, write_anki_csv, write_anki_package
from jlpt_pipeline.validation import load_source


def test_build_anki_notes_creates_two_cards_per_active_entry():
    source = load_source(SAMPLE)
    notes = build_anki_notes(source)
    assert len(notes) == 4
    assert all("ono-003" not in note["guid"] for note in notes)
    assert {note["direction"] for note in notes} == {"ja_to_zh", "zh_to_ja"}


def test_build_anki_notes_escapes_html_values():
    source = load_source(SAMPLE)
    source["entries"][0]["term"] = "<b>&bad</b>"

    notes = build_anki_notes(source)

    assert "&lt;b&gt;&amp;bad&lt;/b&gt;" in notes[0]["front"]
    assert "<b>&bad</b>" not in notes[0]["front"]


def test_build_anki_notes_sanitizes_tags():
    source = load_source(SAMPLE)
    source["entries"][0]["category"] = "sound effect / intense rain"
    source["entries"][0]["jlpt_level_estimate"] = "N1/N2"

    notes = build_anki_notes(source)
    tags = notes[0]["tags"].split()

    assert "n1_n2" in tags
    assert "sound_effect_intense_rain" in tags
    assert all(" " not in tag for tag in tags)


def test_write_anki_csv_skips_rejected_entries(tmp_path):
    source = load_source(SAMPLE)
    output = write_anki_csv(source, tmp_path)
    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows) == 4
    assert rows[0]["direction"] == "ja_to_zh"
    assert all("ざあざあ" not in row["front"] for row in rows)


def test_write_anki_package_creates_apkg(tmp_path):
    source = load_source(SAMPLE)
    output = write_anki_package(source, tmp_path, "Sample JLPT")
    assert output.name == "sample-jlpt.apkg"
    assert output.exists()
    assert output.stat().st_size > 0
