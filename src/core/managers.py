"""Project-level manager subclasses for SharedMemoryModel."""

from __future__ import annotations

from evennia.utils.idmapper.manager import SharedMemoryManager


class ArxSharedMemoryManager(SharedMemoryManager):
    """SharedMemoryManager subclass adding a pk-discovering singleton cache.

    ``.first()`` bypasses the SharedMemoryModel identity map because it isn't a
    pk lookup — every call issues ``SELECT ... LIMIT 1``. ``cached_singleton()``
    does ``.first()`` once, stashes the discovered pk, then serves
    ``.get(pk=stashed_pk)`` on subsequent calls — hitting the identity map
    (zero SQL after the first call).

    If the stashed pk becomes stale (row deleted + recreated),
    ``.get()`` raises ``DoesNotExist`` -> re-discovery via ``.first()``.

    Use on singleton config models (one row per table). Not for multi-row tables.
    """

    _singleton_pk: int | None = None

    def cached_singleton(self):
        """Return the singleton row, cached after the first call.

        Returns ``None`` when no row exists (matching ``.first()`` semantics).
        Callers that need lazy-creation or fail-loud behavior should handle
        ``None`` in their accessor function.
        """
        if self._singleton_pk is not None:
            try:
                return self.get(pk=self._singleton_pk)
            except self.model.DoesNotExist:
                self._singleton_pk = None
        instance = self.first()
        if instance is not None:
            self._singleton_pk = instance.pk
        return instance

    @classmethod
    def flush_singleton_cache(cls) -> None:
        """Clear the stashed singleton pk.

        Called by ``core.testing.flush_test_caches`` between tests so each
        test starts with a fresh singleton cache (mirroring a fresh process).
        """
        cls._singleton_pk = None
