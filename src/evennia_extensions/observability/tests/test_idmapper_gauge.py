"""Tests for evennia_extensions.observability.idmapper_gauge."""

from unittest.mock import patch

from django.test import TestCase


class SnapshotShapeTests(TestCase):
    """snapshot() always returns a well-formed dict."""

    def test_snapshot_returns_dict(self) -> None:
        """Return value is a dict (never raises)."""
        from evennia_extensions.observability.idmapper_gauge import snapshot

        result = snapshot()
        self.assertIsInstance(result, dict)

    def test_snapshot_values_are_two_tuples_of_non_negative_ints(self) -> None:
        """Every value in the returned dict is a (int, int) pair with non-negative values."""
        from evennia_extensions.observability.idmapper_gauge import snapshot

        result = snapshot()
        for label, value in result.items():
            self.assertIsInstance(label, str, msg=f"Key {label!r} is not a str")
            self.assertIsInstance(value, tuple, msg=f"Value for {label!r} is not a tuple")
            self.assertEqual(len(value), 2, msg=f"Value for {label!r} is not a 2-tuple")
            count, approx_bytes = value
            self.assertIsInstance(count, int, msg=f"count for {label!r} is not int")
            self.assertIsInstance(approx_bytes, int, msg=f"approx_bytes for {label!r} is not int")
            self.assertGreaterEqual(count, 0, msg=f"count for {label!r} is negative")
            self.assertGreaterEqual(approx_bytes, 0, msg=f"approx_bytes for {label!r} is negative")

    def test_snapshot_never_raises(self) -> None:
        """snapshot() must not propagate any exception."""
        from evennia_extensions.observability.idmapper_gauge import snapshot

        try:
            snapshot()
        except Exception as exc:  # noqa: BLE001
            self.fail(f"snapshot() raised unexpectedly: {exc!r}")


class StubMeta:
    """Minimal _meta stand-in for a fake model class."""

    def __init__(self, app_label: str) -> None:
        """Initialise with the given app label.

        Args:
            app_label: The Django app label to expose.
        """
        self.app_label = app_label


class FakeCachedModelTests(TestCase):
    """snapshot() counts instances from a fake cached model without DB access."""

    def _make_stub(self, name: str, app_label: str, cache: dict) -> object:
        """Build a plain-object stub that looks like a SharedMemoryModel subclass.

        Args:
            name: The ``__name__`` to assign.
            app_label: The app label to place in the stub ``_meta``.
            cache: The dict to expose as ``__instance_cache__``.

        Returns:
            A namespace object accepted by snapshot()'s subclass walk.
        """

        class _Stub:
            pass

        _Stub.__name__ = name
        _Stub.__module__ = "fake_module"
        _Stub._meta = StubMeta(app_label)
        _Stub.__instance_cache__ = cache
        return _Stub

    def test_counts_a_fake_cached_model(self) -> None:
        """A fake class with two cached instances appears with count == 2."""
        from evennia_extensions.observability.idmapper_gauge import snapshot

        fake_cache = {1: object(), 2: object()}
        stub = self._make_stub("FakeModel", "fake_app", fake_cache)

        # Patch the subclass-walk so snapshot() sees exactly [stub].
        with patch(
            "evennia_extensions.observability.idmapper_gauge._iter_subclasses",
            return_value=[stub],
        ):
            result = snapshot()

        expected_label = "fake_app.FakeModel"
        self.assertIn(expected_label, result, msg=f"Label {expected_label!r} not in {result!r}")
        count, approx_bytes = result[expected_label]
        self.assertEqual(count, 2)
        self.assertGreater(approx_bytes, 0)

    def test_class_without_instance_cache_is_skipped(self) -> None:
        """A stub with no __instance_cache__ is silently skipped, not raised."""
        from evennia_extensions.observability.idmapper_gauge import snapshot

        class _NoCache:
            __name__ = "NoCacheModel"
            __module__ = "fake_module"
            _meta = StubMeta("fake_app")
            # deliberately no __instance_cache__

        with patch(
            "evennia_extensions.observability.idmapper_gauge._iter_subclasses",
            return_value=[_NoCache],
        ):
            result = snapshot()

        self.assertNotIn("fake_app.NoCacheModel", result)

    def test_class_with_asizeof_error_is_skipped(self) -> None:
        """A class whose __instance_cache__ causes asizeof to raise is skipped cleanly."""
        from evennia_extensions.observability.idmapper_gauge import snapshot

        bad_cache = {1: object()}
        stub = self._make_stub("BadSizeModel", "fake_app", bad_cache)

        with (
            patch(
                "evennia_extensions.observability.idmapper_gauge._iter_subclasses",
                return_value=[stub],
            ),
            patch(
                "evennia_extensions.observability.idmapper_gauge._asizeof",
                side_effect=RuntimeError("boom"),
            ),
        ):
            result = snapshot()  # must not raise

        self.assertNotIn("fake_app.BadSizeModel", result)
