"""
SQLite in-memory test settings — fast inner-loop tier.

Inherits from :mod:`server.conf.test_settings` and overrides only the
``DATABASES['default']`` engine to ``django.db.backends.sqlite3`` with an
ephemeral ``:memory:`` database. All other test settings (fast password
hashing, log silencing, ``TEST_ENVIRONMENT=True``, integration_tests app
registration, etc.) flow through from ``test_settings``.

**Why a separate settings file:** the Postgres-only test_settings runs the
full PG matrix locally and in CI. This SQLite tier is for the *inner loop*
— fast test runs while iterating on a feature. Tests that exercise
Postgres-specific features (recursive CTEs, JSONB operators, ``DISTINCT
ON``, window functions, ``ArrayField``, ``pg_trgm``, etc.) must be
decorated with ``@django.test.tag("postgres")`` so this tier skips them
cleanly. The Postgres parity tier — invoked locally via
``arx test --postgres`` and in CI via the existing shard matrix
(``ci.yml:46-76``) — runs every PR and catches everything this tier
skips.

The plan that landed this two-tier model:
``docs/plans/2026-05-20-test-speedups.md``.
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


# Disable migration replay entirely. Django builds the test schema from
# current model state for every app — no migration chain runs at all.
#
# Why: SQLite cannot replay certain ALTER patterns that Postgres handles
# fine (column drops with referencing constraints, materialized views,
# range partitioning). Some apps in this codebase have ~60+ migrations
# with such patterns scattered throughout. Wrapping individual operations
# in vendor guards would touch dozens of files; skipping migration replay
# for the SQLite tier is the same outcome with far less surface.
#
# The PG tier (``arx test --postgres`` and the CI shard matrix at
# ``ci.yml:46-76``) runs the FULL migration chain on every PR and exercises
# every ALTER/RunSQL/RunPython operation, so the carve-out here only
# affects the inner-loop fast tier.
#
# Caveat: ``RunPython`` data seeds (e.g.
# ``world.progression.migrations.0002_social_engagement_kudos_category``)
# do NOT run when migrations are disabled. Tests that depend on a seeded
# lookup row either need (a) explicit seeding in setUpTestData, or (b)
# ``@django.test.tag("postgres")`` so they only run in the PG tier. See
# ``docs/perf/squash-audit-2026-05-20.md`` for the audit of which RunPython
# operations are critical.
class _DisableMigrations:
    """Sentinel: tells Django every app has no migrations."""

    def __contains__(self, item: str) -> bool:
        return True

    def __getitem__(self, item: str) -> None:
        return None


MIGRATION_MODULES = _DisableMigrations()
