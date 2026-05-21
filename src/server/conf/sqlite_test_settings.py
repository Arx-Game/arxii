"""
SQLite in-memory test settings — fast inner-loop tier.

Inherits from :mod:`server.conf.test_settings` and overrides:

* ``DATABASES['default']`` to ``django.db.backends.sqlite3`` ``:memory:``
  for an ephemeral in-process test DB.
* ``MIGRATION_MODULES`` to a ``DisableMigrations`` sentinel so the test
  schema builds from current model state with NO migration replay —
  sidesteps SQLite's inability to replay column-drop-with-constraint
  reorders, materialized view DDL, range-partition setup, etc.
* ``TEST_RUNNER`` to ``SqliteTestRunner`` (in
  :mod:`server.conf.sqlite_test_runner`) which monkey-patches PG-only
  service helpers (REFRESH MATERIALIZED VIEW wrappers) to no-op so
  production code stays free of test-database awareness.

Tests that genuinely require Postgres-specific features (materialized
view *contents*, ``DISTINCT ON``, recursive CTEs, etc.) must be decorated
with ``@django.test.tag("postgres")`` so the SQLite tier skips them
cleanly. The Postgres parity tier (``arx test`` without ``--sqlite``
locally, plus the existing CI shard matrix at ``ci.yml:46-76``) runs the
real migration chain and the real refresh implementations.
"""

from server.conf.test_settings import *  # noqa: F403

# Override the test database to SQLite in-memory. Django auto-creates a
# fresh in-memory DB per test run (and per parallel worker), so no
# ``TEST.TEMPLATE`` or ``TEST.NAME`` overrides are needed.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}

# Use the SQLite-tier runner that monkey-patches PG-only refresh helpers
# to no-op before tests start. See server/conf/sqlite_test_runner.py.
TEST_RUNNER = "server.conf.sqlite_test_runner.SqliteTestRunner"


# Disable migration replay entirely. Django builds the test schema from
# current model state for every app — no migration chain runs at all.
#
# Why: SQLite cannot replay certain ALTER patterns that Postgres handles
# fine (column drops with referencing constraints, materialized views,
# range partitioning). Some apps in this codebase have ~60+ migrations
# with such patterns scattered throughout. Skipping migration replay for
# the SQLite tier sidesteps the issue with no production-code impact.
#
# The PG tier (``arx test`` without ``--sqlite`` and the CI shard matrix
# at ``ci.yml:46-76``) runs the FULL migration chain on every PR and
# exercises every ALTER/RunSQL/RunPython operation, so the carve-out here
# only affects the inner-loop fast tier.
#
# Caveat: ``RunPython`` data seeds (e.g.
# ``world.progression.migrations.0002_social_engagement_kudos_category``)
# do NOT run when migrations are disabled. Tests that depend on a seeded
# lookup row either need (a) explicit seeding in setUpTestData, or (b)
# ``@django.test.tag("postgres")`` so they only run in the PG tier.
class _DisableMigrations:
    """Sentinel: tells Django every app has no migrations."""

    def __contains__(self, item: str) -> bool:
        return True

    def __getitem__(self, item: str) -> None:
        return None


MIGRATION_MODULES = _DisableMigrations()
