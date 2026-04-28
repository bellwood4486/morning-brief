import pytest

from digest.seeds import load_seed


def test_load_seed_returns_file_contents() -> None:
    content = load_seed("summarize_prompt.md")
    assert isinstance(content, str)
    assert len(content) > 0


def test_load_seed_raises_for_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_seed("nonexistent_seed_file.md")
