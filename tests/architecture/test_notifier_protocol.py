"""Notifier Protocol が肥大化していないかを検証する設計遵守テスト (docs/quality.md 層3)。"""

import inspect

from digest.notifiers.base import Notifier


def test_notifier_protocol_can_be_imported() -> None:
    assert Notifier is not None


def test_notifier_protocol_minimal() -> None:
    # inspect.getmembers + predicate=isfunction で Protocol のメソッド一覧を取れる。dunder は除外。
    methods = {
        name
        for name, _ in inspect.getmembers(Notifier, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    assert methods == {"send", "collect_feedback"}
