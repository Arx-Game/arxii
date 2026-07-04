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
that flushes the SharedMemoryModel identity map (and any registered
project-level caches) at the end of every test. Each test then begins
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
    """Flush every SharedMemoryModel subclass's identity map.

    Walks the subclass tree rather than relying on Evennia's signal-shaped
    helper so we can call this from a plain teardown hook without spoofing
    signal kwargs. Uses ``force=False`` to match Evennia's post_migrate signal
    behavior: clear safe (non-dirty) objects, preserve objects with in-flight
    state. This is the same semantics production uses; tests should mirror it.
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
        flusher = getattr(cls, "flush_instance_cache", None)  # noqa: GETATTR_LITERAL
        if flusher is not None:
            with contextlib.suppress(AttributeError, TypeError):
                flusher()  # force=False — match Evennia's signal behavior
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


def _flush_arx_singleton_caches() -> None:
    """Flush every ArxSharedMemoryManager instance's singleton pk cache.

    The pk is cached per-manager-instance (on ``self.__dict__``), so we walk
    the subclass tree to find each concrete manager class, then walk the
    SharedMemoryModel subclass tree to find instantiated managers.
    """
    from evennia.utils.idmapper.models import SharedMemoryModel  # noqa: PLC0415

    from core.managers import ArxSharedMemoryManager  # noqa: PLC0415

    # Collect all ArxSharedMemoryManager subclasses
    arx_mgr_classes: set[type] = set()
    queue: list[type] = [ArxSharedMemoryManager]
    while queue:
        cls = queue.pop()
        if cls in arx_mgr_classes:
            continue
        arx_mgr_classes.add(cls)
        queue.extend(cls.__subclasses__())

    # Walk SharedMemoryModel subclasses to find instantiated managers
    seen: set[type] = set()
    smm_queue: list[type] = [SharedMemoryModel]
    while smm_queue:
        cls = smm_queue.pop()
        if cls in seen:
            continue
        seen.add(cls)
        mgr = getattr(cls, "objects", None)  # noqa: GETATTR_LITERAL
        if mgr is not None and type(mgr) in arx_mgr_classes:
            mgr.flush_singleton_cache()
        smm_queue.extend(cls.__subclasses__())


register_test_cache_flusher(_flush_arx_singleton_caches)
