from pathlib import Path


def test_required_project_files_exist():
    root = Path(__file__).resolve().parents[1]
    required = [
        "requirements.txt",
        "scripts/jlpt_pipeline.py",
        "scripts/jlpt_pipeline/__init__.py",
        "scripts/jlpt_pipeline/models.py",
        "examples/source.sample.json",
        "examples/onomatopoeia_n1_n2_request.md",
    ]
    missing = [path for path in required if not (root / path).exists()]
    assert missing == []
