from pathlib import Path

import pytest
from pydantic import ValidationError

from digest.config import Config

_EXAMPLE_YAML = Path(__file__).resolve().parents[2] / "config.example.yaml"


def test_load_example_yaml() -> None:
    cfg = Config.load(_EXAMPLE_YAML)

    assert cfg.gmail.label == "Newsletter/Tech"
    assert cfg.gmail.processed_label == "Newsletter/Tech/Processed"
    assert cfg.gmail.lookback_hours == 24
    assert cfg.slack.digest_channel == "C0XXXXXXX"
    assert cfg.slack.alerts_channel == "C0YYYYYYY"
    assert cfg.llm.model == "gemini-2.5-flash"


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    yaml_file = tmp_path / "bad.yaml"
    yaml_file.write_text(
        "gmail:\n"
        "  label: x\n"
        "  processed_label: y\n"
        "  lookback_hours: 24\n"
        "  unknown_field: oops\n"
        "slack:\n"
        "  digest_channel: '#d'\n"
        "  alerts_channel: '#a'\n"
        "llm:\n"
        "  model: m\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        Config.load(yaml_file)


def test_missing_required_field_is_rejected(tmp_path: Path) -> None:
    yaml_file = tmp_path / "missing.yaml"
    yaml_file.write_text(
        "gmail:\n"
        "  label: x\n"
        "  processed_label: y\n"
        # lookback_hours is missing
        "slack:\n"
        "  digest_channel: '#d'\n"
        "  alerts_channel: '#a'\n"
        "llm:\n"
        "  model: m\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        Config.load(yaml_file)
