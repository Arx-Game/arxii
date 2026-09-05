"""``BatchedCreateModelMigration`` applies a chunk of CreateModels with one render (ADR-0272).

Profiled 2026-09-05: stock ``Migration.apply`` spent 248 of 259 seconds of a partial
replay re-rendering the related-model closure after every ``CreateModel``; the same
twelve chunks under this base took 29 seconds. These tests pin the contract, not the
speed: the tables exist, the returned state carries the models, and anything that is
not a pure CreateModel chunk goes through Django's own ``apply``.
"""

from __future__ import annotations

from django.db import connection, migrations, models
from django.db.migrations.state import ProjectState
from django.test import TransactionTestCase

from core_management.batched_migration import BatchedCreateModelMigration

APP = "arxii"


def _create(
    name: str, extra_fields: list[tuple[str, models.Field]] | None = None
) -> migrations.CreateModel:
    return migrations.CreateModel(
        name=name,
        fields=[("id", models.AutoField(primary_key=True)), *(extra_fields or [])],
        options={"db_table": f"zz_batched_{name.lower()}"},
    )


class BatchedCreateModelMigrationTests(TransactionTestCase):
    """TransactionTestCase: SQLite's schema editor refuses to run inside a transaction."""

    def setUp(self) -> None:
        self.created: list[str] = []

    def tearDown(self) -> None:
        # Children first: on Postgres the parent cannot go while a FK still points at it.
        with connection.schema_editor() as editor:
            for table in reversed(self.created):
                editor.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')

    def _apply(self, migration: migrations.Migration) -> ProjectState:
        with connection.schema_editor() as editor:
            return migration.apply(ProjectState(), editor)

    def test_pure_create_model_chunk_creates_tables_and_state(self) -> None:
        migration = BatchedCreateModelMigration("zz_batched", APP)
        migration.operations = [
            _create("ZzParent"),
            _create(
                "ZzChild",
                [("parent", models.ForeignKey(f"{APP}.ZzParent", on_delete=models.CASCADE))],
            ),
        ]
        self.created = ["zz_batched_zzparent", "zz_batched_zzchild"]

        state = self._apply(migration)

        tables = set(connection.introspection.table_names())
        assert {"zz_batched_zzparent", "zz_batched_zzchild"} <= tables
        assert (APP, "zzparent") in state.models
        assert (APP, "zzchild") in state.models
        child = state.apps.get_model(APP, "ZzChild")
        assert child._meta.get_field("parent").remote_field.model is state.apps.get_model(
            APP, "ZzParent"
        )

    def test_mixed_chunk_falls_through_to_stock_apply(self) -> None:
        migration = BatchedCreateModelMigration("zz_mixed", APP)
        migration.operations = [
            _create("ZzSolo"),
            migrations.AddField("ZzSolo", "note", models.CharField(max_length=8, default="")),
        ]
        self.created = ["zz_batched_zzsolo"]

        state = self._apply(migration)

        columns = {
            col.name
            for col in connection.introspection.get_table_description(
                connection.cursor(), "zz_batched_zzsolo"
            )
        }
        assert "note" in columns
        assert "note" in state.models[APP, "zzsolo"].fields
