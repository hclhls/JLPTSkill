from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_skill_mentions_required_workflow_terms():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    required = [
        "source.json",
        "verification_status",
        "needs_review",
        "Azure Speech",
        "Obsidian",
        "Anki",
        "video",
    ]
    missing = [item for item in required if item not in text]
    assert missing == []


def test_readme_mentions_azure_environment_variables_and_commands():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    required = [
        "AZURE_SPEECH_KEY",
        "AZURE_SPEECH_REGION",
        "validate",
        "dry-run",
        "build",
        "--tts-provider azure",
    ]
    missing = [item for item in required if item not in text]
    assert missing == []
