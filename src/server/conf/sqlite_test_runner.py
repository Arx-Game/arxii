"""
SQLite inner-loop test runner.

Used by :mod:`server.conf.sqlite_test_settings` (via ``TEST_RUNNER``) so
production code stays free of test-database awareness. Specifically: the
``refresh_*_view()`` helpers (``world.societies.models.refresh_legend_views``,
``world.codex.models.refresh_codex_breadcrumbs``,
``world.areas.models.refresh_area_closure``) execute raw
``REFRESH MATERIALIZED VIEW`` which is PG-only syntax. On the SQLite tier
the views don't exist (their migrations don't run; see ``sqlite_test_settings``
for the ``DisableMigrations`` sentinel). Production code calls these helpers
unconditionally; this runner patches them to no-op before tests start so
SQLite doesn't choke on the unsupported SQL.

**Patching strategy:** ``__code__`` replacement, not module-attribute
re-binding. Several consumer modules (``world.societies.services``,
multiple test modules) imported the functions by name — they hold their
own references that a module-attribute monkey-patch wouldn't reach. By
replacing ``__code__`` directly on the function object, *all* references
(wherever imported from) now execute the no-op body.

Pre-conditions for ``__code__`` replacement: source and target functions
must have compatible signatures (same positional/keyword arg counts, no
closure variables). All three refresh helpers take zero arguments and
have no closures; ``_noop`` matches.

The PG parity tier (``arx test`` without ``--sqlite``, plus CI shards) uses
the default ``DiscoverRunner`` and runs the real refresh implementations
against actual materialized views.
"""

from __future__ import annotations

from typing import Any

from server.conf.test_runner import TimedEvenniaTestRunner


def _noop() -> None:
    """No-op stub used as a ``__code__`` donor for PG-only refresh helpers."""


class SqliteTestRunner(TimedEvenniaTestRunner):
    """Test runner for the SQLite inner-loop tier.

    Extends the project's :class:`TimedEvenniaTestRunner` (which handles
    Evennia's ``_init()``, worker initialization, optional timing wrapper)
    and additionally replaces PG-only ``REFRESH MATERIALIZED VIEW``
    helpers with no-ops at ``setup_test_environment`` time. The patches
    persist for the lifetime of the test run.
    """

    def setup_test_environment(self, **kwargs: Any) -> None:
        """Install the SQLite-tier monkey-patches after Evennia/Django setup."""
        super().setup_test_environment(**kwargs)
        self._install_sqlite_noops()

    @staticmethod
    def _install_sqlite_noops() -> None:
        """Replace the three refresh helpers' ``__code__`` with the no-op body.

        Imported lazily inside the method so this module can be imported
        before Django's app registry is ready (settings load earlier than
        models).
        """
        from world.areas.models import refresh_area_closure  # noqa: PLC0415
        from world.codex.models import refresh_codex_breadcrumbs  # noqa: PLC0415
        from world.societies.models import refresh_legend_views  # noqa: PLC0415

        refresh_legend_views.__code__ = _noop.__code__
        refresh_codex_breadcrumbs.__code__ = _noop.__code__
        refresh_area_closure.__code__ = _noop.__code__
