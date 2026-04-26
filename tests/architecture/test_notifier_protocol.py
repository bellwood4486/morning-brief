import inspect

from digest.notifiers.base import Notifier


def test_notifier_protocol_can_be_imported() -> None:
    assert Notifier is not None


def test_notifier_protocol_minimal() -> None:
    methods = {
        name
        for name, _ in inspect.getmembers(Notifier, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    assert methods == {"send", "collect_feedback"}
