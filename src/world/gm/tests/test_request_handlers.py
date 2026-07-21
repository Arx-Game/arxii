"""Table-request kind->handler registry (#2607)."""

from django.test import SimpleTestCase

from world.gm.request_handlers import (
    REQUEST_HANDLERS,
    UnregisteredRequestKindError,
    register_request_handler,
    run_request_completion,
)


class _FakeRequest:
    def __init__(self, kind: str) -> None:
        self.kind = kind


class RegistryTests(SimpleTestCase):
    def test_register_and_dispatch(self) -> None:
        seen: list[object] = []
        register_request_handler("test_kind", seen.append)
        try:
            run_request_completion(_FakeRequest("test_kind"))
            assert len(seen) == 1
        finally:
            REQUEST_HANDLERS.pop("test_kind", None)

    def test_unregistered_raises(self) -> None:
        with self.assertRaises(UnregisteredRequestKindError):
            run_request_completion(_FakeRequest("nope_kind"))
