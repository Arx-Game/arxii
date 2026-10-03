"""The #4091 backfill sets allegiance by the historical names, once."""

from importlib import import_module

from django.apps import apps
from django.test import TestCase

from world.conditions.constants import Allegiance
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionTemplate

_migration = import_module("world.migrations.0194_backfill_sets_allegiance")


class BackfillTests(TestCase):
    def test_sets_both_rows(self):
        charmed = ConditionTemplateFactory(name="Charmed")
        calm = ConditionTemplateFactory(name="Calm")
        _migration.forwards(apps, None)
        # forwards() writes via update_with_reason (a raw UPDATE, required because
        # ConditionTemplate is a SharedMemoryModel), which bypasses the identity map,
        # so the cached instances must be flushed before refresh_from_db() can see it.
        ConditionTemplate.flush_instance_cache()
        charmed.refresh_from_db()
        calm.refresh_from_db()
        self.assertEqual(charmed.sets_allegiance, Allegiance.ALLY_OF_CASTER)
        self.assertEqual(calm.sets_allegiance, Allegiance.NEUTRAL)

    def test_leaves_authored_values(self):
        charmed = ConditionTemplateFactory(name="Charmed", sets_allegiance=Allegiance.TURNED)
        _migration.forwards(apps, None)
        ConditionTemplate.flush_instance_cache()
        charmed.refresh_from_db()
        self.assertEqual(charmed.sets_allegiance, Allegiance.TURNED)
