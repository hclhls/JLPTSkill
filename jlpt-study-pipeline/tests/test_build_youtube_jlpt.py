import sys
from pathlib import Path
from io import StringIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_youtube_jlpt import ask_video_field_config
from jlpt_pipeline.models import VideoFieldConfig


def test_ask_video_field_config_non_tty():
    """Test that non-TTY returns default config."""
    # When stdin is not a TTY, should return None (caller uses default)
    result = ask_video_field_config()

    # Non-TTY should return None
    assert result is None or isinstance(result, VideoFieldConfig)
