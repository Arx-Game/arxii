"""Migration helpers shared across apps.

This module provides utilities for Django migrations that need to behave
differently depending on the database backend. In particular,
:class:`PostgresOnlyRunSQL` is a drop-in replacement for ``RunSQL`` that
skips execution on non-Postgres backends — useful for materialized views,
table partitioning, and other features that don't exist on SQLite.

Why this matters: the project's inner-loop test tier uses SQLite in-memory
(`sqlite_test_settings`). Any migration that runs raw Postgres-specific
SQL via plain ``RunSQL`` will fail at test-DB setup time on SQLite and
block the entire test run. Wrapping such SQL in ``PostgresOnlyRunSQL``
lets the migration apply cleanly as a no-op on SQLite while still doing
the right thing on the Postgres parity tier (local
``arx test --postgres`` and CI shards).

Tests that query the resulting PG-only objects (materialized views,
partitioned tables) MUST be decorated with ``@django.test.tag("postgres")``
so the SQLite tier skips them; the data won't exist on SQLite. This
module only handles the schema side.

See ``docs/plans/2026-05-20-test-speedups.md`` for the two-tier rationale.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.migrations.operations.special import RunSQL

# Django's canonical vendor name for Postgres backends — compared against
# ``connection.vendor`` to gate PG-only schema operations.
_POSTGRES_VENDOR = "postgresql"  # noqa: STRING_LITERAL — Django backend vendor identifier

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import ProjectState


class PostgresOnlyRunSQL(RunSQL):
    """``RunSQL`` that no-ops on non-Postgres backends.

    Use exactly like ``migrations.RunSQL`` — same ``sql``, ``reverse_sql``,
    and (optionally) ``state_operations`` arguments. On Postgres the SQL
    runs as normal. On SQLite (or any other vendor) both the forward and
    backward operations are skipped silently, allowing the migration
    chain to apply without errors.

    Example::

        from core_management.migration_utils import PostgresOnlyRunSQL

        class Migration(migrations.Migration):
            dependencies = [("foo", "0001_initial")]
            operations = [
                PostgresOnlyRunSQL(
                    sql=_read_sql("create_materialized_view.sql"),
                    reverse_sql="DROP MATERIALIZED VIEW IF EXISTS foo_mv;",
                ),
            ]
    """

    def database_forwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        """Run the SQL only on Postgres; no-op everywhere else."""
        if schema_editor.connection.vendor != _POSTGRES_VENDOR:
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        """Run the reverse SQL only on Postgres; no-op everywhere else."""
        if schema_editor.connection.vendor != _POSTGRES_VENDOR:
            return
        super().database_backwards(app_label, schema_editor, from_state, to_state)
