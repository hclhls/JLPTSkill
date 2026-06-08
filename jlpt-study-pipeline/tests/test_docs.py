from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_skill_mentions_required_workflow_terms():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    required = [
        "source.json",
        "verification_status",
        "needs_review",
        "edge-tts",
        "Obsidian",
        "Anki",
        "video",
    ]
    missing = [item for item in required if item not in text]
    assert missing == []


def test_readme_mentions_edge_tts_and_commands():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    required = [
        "edge-tts",
        "validate",
        "dry-run",
        "build",
        "--tts-provider edge",
        "--tts-provider none",
    ]
    missing = [item for item in required if item not in text]
    assert missing == []
