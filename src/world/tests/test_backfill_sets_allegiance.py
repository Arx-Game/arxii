"""The #4091 backfill sets allegiance by the historical names, once.

``forwards()`` runs against Django's frozen historical model during a real
``migrate`` -- a plain ``Manager``/``QuerySet``, no identity map, no custom querysets
(``ArxSharedMemoryManager`` is never carried into migration state: nothing sets
``use_in_migrations`` and the migration declares no ``managers=[...]``). So these
tests build that same historical ``apps`` registry via ``MigrationExecutor`` and run
``forwards()`` against it, instead of the live ``django.apps.apps`` -- the live
registry has the real identity-map-guarded manager and would pass even if
``forwards()`` called a method the historical model doesn't have.
"""

from importlib import import_module

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, override_settings

from world.conditions.constants import Allegiance
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionTemplate

_migration = import_module("world.migrations.0196_backfill_sets_allegiance")


def _historical_apps():
    """The real historical ``apps`` registry as of this migration, as `migrate` uses it.

    The SQLite fast tier sets ``MIGRATION_MODULES`` to a sentinel that disables
    migration replay entirely (``server/conf/sqlite_test_settings.py``), so the
    loader would otherwise treat ``arxii`` as having no migrations at all and
    raise ``NodeNotFoundError``. Clearing that override here (real disk-based
    migrations) only affects how this one ``MigrationLoader`` renders *state* --
    it never re-runs DDL against the already-built test schema, which already
    matches this migration's end state.
    """
    with override_settings(MIGRATION_MODULES={}):
        loader = MigrationExecutor(connection).loader
        return loader.project_state(("arxii", "0196_backfill_sets_allegiance")).apps


class BackfillTests(TestCase):
    def test_sets_both_rows(self):
        charmed = ConditionTemplateFactory(name="Charmed")
        calm = ConditionTemplateFactory(name="Calm")
        _migration.forwards(_historical_apps(), None)
        # The historical model's raw UPDATE bypasses the live identity map, so the
        # cached instances must be flushed before refresh_from_db() can see it.
        ConditionTemplate.flush_instance_cache()
        charmed.refresh_from_db()
        calm.refresh_from_db()
        self.assertEqual(charmed.sets_allegiance, Allegiance.ALLY_OF_CASTER)
        self.assertEqual(calm.sets_allegiance, Allegiance.NEUTRAL)

    def test_leaves_authored_values(self):
        charmed = ConditionTemplateFactory(name="Charmed", sets_allegiance=Allegiance.TURNED)
        _migration.forwards(_historical_apps(), None)
        ConditionTemplate.flush_instance_cache()
        charmed.refresh_from_db()
        self.assertEqual(charmed.sets_allegiance, Allegiance.TURNED)
