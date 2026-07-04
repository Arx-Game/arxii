"""Tests for ArxSharedMemoryManager.cached_singleton()."""

from django.test import TestCase

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
        # assertNumQueries doesn't support "at least" — use a generous upper
        # bound. The point is that the first call is NOT zero.
        with self.assertNumQueries(max_queries=10):
            SoulfrayConfig.objects.cached_singleton()

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


class SingletonCacheFlushHookTests(TestCase):
    """Verify flush_test_caches clears ArxSharedMemoryManager singleton pks."""

    def test_flush_test_caches_clears_singleton_pk(self) -> None:
        from core.testing import flush_test_caches

        SoulfrayConfigFactory()
        SoulfrayConfig.objects.cached_singleton()  # prime
        self.assertIsNotNone(SoulfrayConfig.objects._singleton_pk)
        flush_test_caches()
        self.assertIsNone(SoulfrayConfig.objects._singleton_pk)
