"""Migration 0416: the drift correction rite's stored service path follows its function's
rename (#5124). Staff-authored ``Ritual`` rows keep working; nothing else is touched."""

from importlib import import_module

from django.apps import apps
from django.test import TestCase

from world.magic.factories import RitualFactory
from world.magic.models import Ritual

MIGRATION = import_module("world.migrations.0416_rite_of_settling_service_path")


class RiteOfSettlingServicePathMigrationTests(TestCase):
    def path_of(self, ritual: Ritual) -> str:
        return Ritual.objects.get(pk=ritual.pk).service_function_path

    def test_every_row_holding_the_old_path_takes_the_new_one_and_no_other_row_moves(self) -> None:
        old_a = RitualFactory(service_function_path=MIGRATION.OLD_PATH)
        old_b = RitualFactory(service_function_path=MIGRATION.OLD_PATH)
        other = RitualFactory(service_function_path="world.magic.services.placeholder_ritual")

        MIGRATION.to_settling_rite(apps, None)

        self.assertEqual(self.path_of(old_a), MIGRATION.NEW_PATH)
        self.assertEqual(self.path_of(old_b), MIGRATION.NEW_PATH)
        self.assertEqual(self.path_of(other), "world.magic.services.placeholder_ritual")

    def test_running_it_again_or_with_no_match_changes_nothing(self) -> None:
        done = RitualFactory(service_function_path=MIGRATION.NEW_PATH)

        MIGRATION.to_settling_rite(apps, None)
        MIGRATION.to_settling_rite(apps, None)

        self.assertEqual(self.path_of(done), MIGRATION.NEW_PATH)

    def test_it_changes_nothing_on_an_empty_database(self) -> None:
        MIGRATION.to_settling_rite(apps, None)

        self.assertFalse(Ritual.objects.exists())

    def test_reversing_restores_the_old_path(self) -> None:
        ritual = RitualFactory(service_function_path=MIGRATION.NEW_PATH)

        MIGRATION.to_drift_correction_rite(apps, None)

        self.assertEqual(self.path_of(ritual), MIGRATION.OLD_PATH)
