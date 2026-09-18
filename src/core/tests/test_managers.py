"""Tests for ArxSharedMemoryManager.cached_singleton() and cached_all()."""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from core.managers import SharedMemoryWriteError
from world.boards.models import BoardPost
from world.magic.factories import SoulfrayConfigFactory
from world.magic.models.soulfray import SoulfrayConfig


class CachedSingletonTests(TestCase):
    """Verify cached_singleton caches via the SharedMemoryModel identity map."""

    def setUp(self) -> None:
        SoulfrayConfig.objects.flush_singleton_cache()

    def test_first_call_hits_db(self) -> None:
        """First cached_singleton() call issues at least one query."""
        SoulfrayConfigFactory()
        SoulfrayConfig.objects.flush_singleton_cache()
        # Clear the identity map so .get(pk=) won't find a cached instance
        SoulfrayConfig.flush_instance_cache()
        # assertNumQueries takes an exact count, not "at least" -- use
        # CaptureQueriesContext with a generous upper bound instead. The
        # point is that the first call is NOT zero.
        with CaptureQueriesContext(connection) as ctx:
            SoulfrayConfig.objects.cached_singleton()
        self.assertGreaterEqual(len(ctx.captured_queries), 1)
        self.assertLessEqual(len(ctx.captured_queries), 10)

    def test_second_call_hits_identity_map_zero_queries(self) -> None:
        """Second cached_singleton() call issues zero queries."""
        SoulfrayConfigFactory()
        SoulfrayConfig.objects.flush_singleton_cache()
        SoulfrayConfig.flush_instance_cache()
        # Prime the cache
        SoulfrayConfig.objects.cached_singleton()
        # Second call: pk is stashed, .get(pk=) hits identity map
        with self.assertNumQueries(0):
            SoulfrayConfig.objects.cached_singleton()

    def test_returns_none_when_no_row(self) -> None:
        """cached_singleton returns None when no row exists."""
        result = SoulfrayConfig.objects.cached_singleton()
        self.assertIsNone(result)

    def test_stale_pk_triggers_rediscovery(self) -> None:
        """If the stashed pk becomes stale, cached_singleton re-discovers."""
        config = SoulfrayConfigFactory()
        SoulfrayConfig.objects.flush_singleton_cache()
        SoulfrayConfig.flush_instance_cache()
        # Prime
        result = SoulfrayConfig.objects.cached_singleton()
        self.assertIsNotNone(result)
        # Simulate stale pk: flush the identity map and corrupt the stashed pk
        SoulfrayConfig.flush_instance_cache()
        # Force a bad pk into the cache to simulate deletion
        SoulfrayConfig.objects._singleton_pk = 999_999
        # Re-discovery should still find the real row
        result = SoulfrayConfig.objects.cached_singleton()
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, config.pk)


class CachedAllTests(TestCase):
    """Verify cached_all() caches the full table via the identity map."""

    def setUp(self) -> None:
        SoulfrayConfig.objects.flush_all_cache()
        SoulfrayConfig.flush_instance_cache()

    def test_first_call_hits_db(self) -> None:
        """First cached_all() call issues at least one query."""
        SoulfrayConfigFactory()
        SoulfrayConfig.objects.flush_all_cache()
        SoulfrayConfig.flush_instance_cache()
        # assertNumQueries takes an exact count, not "at least" -- use
        # CaptureQueriesContext with a generous upper bound instead.
        with CaptureQueriesContext(connection) as ctx:
            SoulfrayConfig.objects.cached_all()
        self.assertGreaterEqual(len(ctx.captured_queries), 1)
        self.assertLessEqual(len(ctx.captured_queries), 10)

    def test_second_call_hits_identity_map_zero_queries(self) -> None:
        """Second cached_all() call issues zero queries."""
        SoulfrayConfigFactory()
        SoulfrayConfig.objects.flush_all_cache()
        SoulfrayConfig.flush_instance_cache()
        SoulfrayConfig.objects.cached_all()  # prime
        with self.assertNumQueries(0):
            SoulfrayConfig.objects.cached_all()

    def test_returns_every_row(self) -> None:
        """cached_all() returns every row in the table, not just one."""
        first = SoulfrayConfigFactory()
        second = SoulfrayConfigFactory()
        result = SoulfrayConfig.objects.cached_all()
        self.assertCountEqual([r.pk for r in result], [first.pk, second.pk])

    def test_row_created_after_first_load_is_visible_on_next_call(self) -> None:
        """A row created via .create() after cached_all() has already loaded
        self-registers in __instance_cache__ -- no explicit registration call
        needed, unlike BattleStateCache (see Task 4)."""
        first = SoulfrayConfigFactory()
        SoulfrayConfig.objects.cached_all()  # prime with 1 row
        second = SoulfrayConfigFactory()  # created after the cache warmed
        result = SoulfrayConfig.objects.cached_all()
        self.assertCountEqual([r.pk for r in result], [first.pk, second.pk])


class SingletonCacheFlushHookTests(TestCase):
    """Verify flush_test_caches clears ArxSharedMemoryManager singleton pks."""

    def test_flush_test_caches_clears_singleton_pk(self) -> None:
        from core.testing import flush_test_caches

        SoulfrayConfigFactory()
        SoulfrayConfig.objects.cached_singleton()  # prime
        self.assertIsNotNone(SoulfrayConfig.objects.__dict__.get("_singleton_pk"))
        flush_test_caches()
        self.assertIsNone(SoulfrayConfig.objects.__dict__.get("_singleton_pk"))

    def test_flush_test_caches_clears_all_loaded_flag(self) -> None:
        from core.testing import flush_test_caches

        SoulfrayConfigFactory()
        SoulfrayConfig.objects.cached_all()  # prime
        self.assertTrue(SoulfrayConfig.objects.__dict__.get("_all_loaded"))
        flush_test_caches()
        self.assertFalse(SoulfrayConfig.objects.__dict__.get("_all_loaded"))


class SharedMemoryWriteGuardTests(TestCase):
    """Require explicit reasons for queryset writes on project idmapped models."""

    def test_update_requires_reason(self) -> None:
        """A raw queryset update is rejected before it can stale the identity map."""
        config = SoulfrayConfigFactory(severity_scale=10)

        with self.assertRaises(SharedMemoryWriteError):
            SoulfrayConfig.objects.filter(pk=config.pk).update(severity_scale=20)

        self.assertEqual(
            SoulfrayConfig.objects.values_list("severity_scale", flat=True).get(pk=config.pk),
            10,
        )

    def test_custom_as_manager_queryset_is_guarded(self) -> None:
        """Custom querysets retain the write guard when exposed as managers."""
        with self.assertRaises(SharedMemoryWriteError):
            BoardPost.objects.filter(pk=0).update(title="stale")

    def test_update_with_reason_writes(self) -> None:
        """The named escape writes after recording a non-empty reason."""
        config = SoulfrayConfigFactory(severity_scale=10)

        updated = SoulfrayConfig.objects.filter(pk=config.pk).update_with_reason(
            reason="test fixture needs a direct database write",
            severity_scale=20,
        )

        self.assertEqual(updated, 1)
        self.assertEqual(
            SoulfrayConfig.objects.values_list("severity_scale", flat=True).get(pk=config.pk),
            20,
        )

    def test_blank_reason_is_rejected(self) -> None:
        """The explicit escape cannot be used without a stated reason."""
        config = SoulfrayConfigFactory()

        with self.assertRaises(ValueError):
            SoulfrayConfig.objects.filter(pk=config.pk).update_with_reason(
                reason="   ", severity_scale=20
            )

    def test_bulk_update_requires_reason_and_escape_handles_batches(self) -> None:
        """Bulk updates guard each internal SQL update and support the escape."""
        first = SoulfrayConfigFactory(severity_scale=10)
        second = SoulfrayConfigFactory(severity_scale=20)

        first.severity_scale = 11
        second.severity_scale = 21
        with self.assertRaises(SharedMemoryWriteError):
            SoulfrayConfig.objects.bulk_update([first, second], ["severity_scale"], batch_size=1)

        updated = SoulfrayConfig.objects.bulk_update_with_reason(
            [first, second],
            ["severity_scale"],
            batch_size=1,
            reason="test fixture needs a direct bulk database write",
        )

        self.assertEqual(updated, 2)
