"""Test-infrastructure helpers that align test behavior with production semantics.

## Why this exists

Production runs ``SharedMemoryModel`` with a persistent Python identity map
backed by a persistent database. Both live as long as the process. A cache
that maps name → PK (e.g. ``ConditionTemplate.get_by_name`` lookups) is safe
because rows aren't deleted out from under the cache.

Tests using ``TestCase`` create rows in a transaction, then roll back at the
end of each test. That clears the database — but it does NOT clear the
SharedMemoryModel identity map (which is a Python-level cache that knows
nothing about transactions). Result: a row created in test_A leaves a
stale Python object in the identity map for test_B, with a PK that no
longer corresponds to any DB row.

This is a **test-only invented state** that production never reaches. Code
optimized for production cache stability (the right design) can break in
tests purely because of this asymmetry — the cache returns a stale Python
object, validation passes (object name unchanged), and downstream FK
inserts blow up because the stale PK isn't in the database.

The fix below installs a teardown hook in :class:`TimedEvenniaTestRunner`
that empties the SharedMemoryModel identity map, every instance, safe or
not (and any registered project-level caches) at the end of every test. Each test then begins
with the same fresh-process state as a real production restart, and
production-correct caches stay production-correct in tests.

## Adding your own cache

Module-level setup::

    from core.testing import register_test_cache_flusher

    def _my_cache_clear() -> None:
        MyModel._my_name_cache.clear()

    register_test_cache_flusher(_my_cache_clear)

The registered callable runs once after each test's ``_post_teardown``,
before the next test's ``setUp``.
"""

from __future__ import annotations

from collections.abc import Callable
import contextlib

_custom_cache_flushers: list[Callable[[], None]] = []


def register_test_cache_flusher(fn: Callable[[], None]) -> None:
    """Register a callable that :func:`flush_test_caches` will invoke.

    Use this when adding a Python-side cache (e.g. a name→PK map on a
    model manager) that needs to be cleared between tests to mirror the
    fresh-process semantics of production.

    Idempotent: registering the same callable twice has no extra effect.
    """
    if fn not in _custom_cache_flushers:
        _custom_cache_flushers.append(fn)


def _flush_sharedmemorymodel_caches() -> None:
    """Drop every cached SharedMemoryModel instance, safe or not.

    Walks the subclass tree rather than relying on Evennia's signal-shaped
    helper so we can call this from a plain teardown hook without spoofing
    signal kwargs.

    The flush is forced (#3657 tranche 1, ruled 2026-10-15). Evennia's own
    flush keeps every object whose ``at_idmapper_flush`` says it carries
    in-flight state, which for a typeclassed object means any NAttribute, and
    the command handler sets ``ndb.last_cmd`` on whoever typed a line. So a
    character that ran one command in test_A survived the per-test flush and
    was still cached, with no row behind it, when test_B asked for
    ``settings.DEFAULT_HOME`` by pk: ``SharedMemoryManager.get`` answers a pk
    lookup from the cache without a query, and test_B wrote a home the
    database did not hold. Ten magic tests died that way on PR #4360's first
    two CI runs, each time in a different worker. In-flight state is a
    property of a live server; between two tests there is none worth keeping.
    """
    # Imported lazily so this module is importable in environments where
    # Evennia isn't available (e.g. tool scripts that import core.testing).
    from evennia.utils.idmapper.models import SharedMemoryModel  # noqa: PLC0415

    seen: set[type] = set()
    queue: list[type] = [SharedMemoryModel]
    while queue:
        cls = queue.pop()
        if cls in seen:
            continue
        seen.add(cls)
        # Abstract subclasses or those without a concrete ``__dbclass__``
        # may not implement ``flush_instance_cache`` cleanly; skip them
        # rather than fail the entire teardown.
        # Suppression justified: duck-typed SharedMemoryModel subclass-tree walk; abstract classes
        # lack it.
        flusher = getattr(cls, "flush_instance_cache", None)  # noqa: GETATTR_LITERAL
        if flusher is not None:
            with contextlib.suppress(AttributeError, TypeError):
                flusher(force=True)
        queue.extend(cls.__subclasses__())


def flush_test_caches() -> None:
    """Flush SharedMemoryModel + all registered custom caches.

    Called by :class:`server.conf.test_runner.TimedEvenniaTestRunner` from
    each test's ``_post_teardown`` hook. Don't call this from production
    code — it's a test-lifecycle hook.
    """
    _flush_sharedmemorymodel_caches()
    for flusher in _custom_cache_flushers:
        flusher()


def _flush_arx_manager_caches() -> None:
    """Flush every CachedAllMixin/ArxSharedMemoryManager instance's caches.

    Walks the SharedMemoryModel subclass tree to find instantiated managers.
    A manager instance is flushed for whichever caches it actually has:
    ``flush_all_cache()`` (CachedAllMixin -- full-table cache, #1846) and/or
    ``flush_singleton_cache()`` (ArxSharedMemoryManager -- singleton pk cache,
    #1741). Some managers (e.g. ModifierTargetManager, IntensityTierManager)
    mix in CachedAllMixin without being an ArxSharedMemoryManager, so both
    checks run independently rather than gating on one type.
    """
    from evennia.utils.idmapper.models import SharedMemoryModel  # noqa: PLC0415

    from core.managers import ArxSharedMemoryManager, CachedAllMixin  # noqa: PLC0415

    seen: set[type] = set()
    smm_queue: list[type] = [SharedMemoryModel]
    while smm_queue:
        cls = smm_queue.pop()
        if cls in seen:
            continue
        seen.add(cls)
        # Suppression justified: duck-typed SharedMemoryModel subclass-tree walk; abstract classes
        # lack it.
        mgr = getattr(cls, "objects", None)  # noqa: GETATTR_LITERAL
        if isinstance(mgr, CachedAllMixin):
            mgr.flush_all_cache()
        if isinstance(mgr, ArxSharedMemoryManager):
            mgr.flush_singleton_cache()
        smm_queue.extend(cls.__subclasses__())


register_test_cache_flusher(_flush_arx_manager_caches)


def _flush_natural_key_indexes() -> None:
    """Clear the natural-key -> pk indexes and lookup-table warm flags (#2687).

    Replaces the per-model registrations previously made by
    ``world.conditions.apps`` and ``world.traits.apps`` for their bespoke name
    caches, both of which this index subsumes.
    """
    from core.natural_keys import flush_natural_key_indexes  # noqa: PLC0415

    flush_natural_key_indexes()


register_test_cache_flusher(_flush_natural_key_indexes)


def _flush_result_chart_cache() -> None:
    """Drop ``ResultChart``'s class-level chart cache (#3657 tranche 1).

    ``ResultChart.get_chart_for_difference`` fills ``_chart_cache`` from the
    table on first use and never refills it, so the charts one test built
    answered every later check in the process after their rows were rolled
    back: a dead chart has no outcome rows, and the roll resolved to nothing.
    """
    from world.traits.models import ResultChart  # noqa: PLC0415

    ResultChart._chart_cache.clear()


register_test_cache_flusher(_flush_result_chart_cache)
