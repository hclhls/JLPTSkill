#!/usr/bin/env python3
"""Quick verification script for Task 1 implementation."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

from jlpt_pipeline.models import VideoFieldConfig

# Test 1: defaults
config = VideoFieldConfig()
assert config.term_count == 2
assert config.meaning_count == 1
assert config.example_count == 1
assert config.show_example_translation is True
assert config.term_order == 1
assert config.meaning_order == 2
assert config.example_order == 3
print("✓ Test 1 (defaults) passed")

# Test 2: custom values
config = VideoFieldConfig(
    term_count=3,
    meaning_count=2,
    example_count=2,
    show_example_translation=False,
    term_order=2,
    meaning_order=1,
    example_order=3,
)
assert config.term_count == 3
assert config.meaning_count == 2
assert config.example_count == 2
assert config.show_example_translation is False
assert config.term_order == 2
assert config.meaning_order == 1
assert config.example_order == 3
print("✓ Test 2 (custom values) passed")

# Test 3: ordered_fields
config = VideoFieldConfig(
    term_order=3,
    meaning_order=1,
    example_order=2,
)
ordered = config.ordered_fields()
assert ordered == [
    ("meaning", 1),
    ("example", 2),
    ("term", 3),
]
print("✓ Test 3 (ordered_fields) passed")

print("\nAll 3 tests passed successfully!")
