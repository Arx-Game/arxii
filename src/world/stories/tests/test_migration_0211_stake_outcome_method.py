"""Tests for migration 0211's rewrite_gm_pick_rows RunPython (#3561).

Restructure of the retired GM constrained pick: every StakeOutcome row still
holding method="gm_pick" is rewritten to method="machine" so the enum's
remaining MACHINE-only value is legal on every row. resolved_by and gm_notes
are untouched - they're historical audit fields now.

Uses django.apps.apps directly against the real, current model classes (the
enum member removal is the only schema change here and rows are rewritten by
pk), per the running-tests convention for this repo (no MigrationExecutor
precedent exists in the test suite for a data-only RunPython) - matches
test_migration_0207_remove_pending_review.py.
"""

import importlib

from django.apps import apps as django_apps
from evennia.utils.test_resources import EvenniaTestCase

from world.gm.factories import GMProfileFactory
from world.stories.constants import StakeOutcomeMethod, StakeResolutionColumn
from world.stories.factories import StakeOutcomeFactory
from world.stories.models import StakeOutcome

_migration = importlib.import_module("world.migrations.0211_retire_stake_outcome_gm_pick")


class RewriteGmPickRowsTests(EvenniaTestCase):
    """world.migrations.0211_retire_stake_outcome_gm_pick.rewrite_gm_pick_rows"""

    def _run(self):
        _migration.rewrite_gm_pick_rows(django_apps, None)
        # The RunPython's own StakeOutcome.objects.filter(...).update(...) call
        # is correct against the DB (a real `migrate` run has no live instances
        # to go stale), but this test builds its row via a factory first, so
        # the idmapper identity-map cache holds a pre-update instance. Flush it
        # so refresh_from_db() below (which idmapper's SharedMemoryManager.get()
        # also serves from cache) reflects what the migration actually wrote.
        StakeOutcome.flush_instance_cache(force=True)

    def test_gm_pick_row_becomes_machine_and_audit_fields_survive(self):
        gm = GMProfileFactory()
        outcome = StakeOutcomeFactory(
            column=StakeResolutionColumn.WIN,
            method=StakeOutcomeMethod.MACHINE,
            resolved_by=gm,
            gm_notes="They earned it.",
        )
        # Force the pre-migration value the factory's own choices no longer
        # allow - mirrors a row written back when GM_PICK still existed.
        StakeOutcome.objects.filter(pk=outcome.pk).update(method="gm_pick")

        self._run()

        outcome.refresh_from_db()
        self.assertEqual(outcome.method, StakeOutcomeMethod.MACHINE)
        self.assertEqual(outcome.resolved_by_id, gm.pk)
        self.assertEqual(outcome.gm_notes, "They earned it.")

    def test_machine_row_is_untouched(self):
        outcome = StakeOutcomeFactory(
            column=StakeResolutionColumn.LOSS, method=StakeOutcomeMethod.MACHINE
        )

        self._run()

        outcome.refresh_from_db()
        self.assertEqual(outcome.method, StakeOutcomeMethod.MACHINE)
        self.assertIsNone(outcome.resolved_by_id)
        self.assertEqual(outcome.gm_notes, "")
