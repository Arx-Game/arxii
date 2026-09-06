"""A migration base that applies a chunk of ``CreateModel`` ops with one render (ADR-0276).

Stock ``Migration.apply`` runs each operation's ``state_forwards`` against a
project state whose ``apps`` are already rendered, so ``ProjectState.add_model``
calls ``reload_model`` and Django re-renders the *transitive closure* of models
related to the new one: on this schema a model with FKs to a hub pulls in most
of the graph, so every ``CreateModel`` costs O(models created so far) and a
1,100-model chain costs O(n^2). Profiled 2026-09-05: 248 of 259 seconds of a
partial replay were that re-render (``state.render_multiple`` -> ``Field.clone``).

For a migration whose operations are all ``CreateModel``, none of those
intermediate renders is observable: ``CreateModel.database_forwards`` only needs
the new model's rendered class, and the state after the last operation is what
the next migration reads. So this base drops the rendered ``apps`` from a clone
of the incoming state, runs every ``state_forwards`` (cheap without ``apps``),
renders once, and only then runs each operation's DDL against that final state.
Operations run in list order, so a FK's target table always exists by the time
its owner is created (the inliner emits models in topological order).

Anything else (a mixed migration, ``sqlmigrate``'s ``collect_sql``, a backend
without transactional DDL) falls through to stock ``apply`` unchanged. Backwards
application is untouched: ``unapply`` is Django's.
"""

from __future__ import annotations

from typing import Any

from django.db import migrations
from django.db.migrations.operations.models import CreateModel
from django.db.migrations.state import ProjectState


class BatchedCreateModelMigration(migrations.Migration):
    """``Migration`` whose forward apply renders the project state once per chunk."""

    def apply(
        self, project_state: ProjectState, schema_editor: Any, collect_sql: bool = False
    ) -> ProjectState:
        batchable = (
            not collect_sql
            and schema_editor.atomic_migration
            and bool(self.operations)
            and all(type(op) is CreateModel for op in self.operations)
        )
        if not batchable:
            return super().apply(project_state, schema_editor, collect_sql)

        state = project_state.clone()
        # Without rendered apps, add_model records the model state and reloads nothing.
        state.__dict__.pop("apps", None)
        for operation in self.operations:
            operation.state_forwards(self.app_label, state)
        state.apps  # noqa: B018 - one render of the whole state, on purpose
        for operation in self.operations:
            # CreateModel.database_forwards reads only to_state; from_state is unused.
            operation.database_forwards(self.app_label, schema_editor, state, state)
        return state
