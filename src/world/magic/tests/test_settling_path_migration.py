"""Migration for the rite of settling's service path: the drift correction rite's stored path
follows its function's rename (#5124). Staff-authored ``Ritual`` rows keep working; nothing
else is touched.

The migration runs on historical models, whose manager allows ``update()``; the live idmapper
manager refuses it. These tests hand the migration the live model's plain base manager in the
historical model's place, so what is checked is the rewrite itself. The module is found by its
name without its number, so the number can move when the migration is renumbered after
another one lands first. (The SQLite test tier runs with migrations disabled, so the
migration is not applied by the test database.)
"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

from django.test import TestCase

from world.magic.constants import RitualExecutionKind
from world.magic.models import Ritual


def _load_migration():
    here = Path(__file__).resolve().parents[2] / "migrations"
    (path,) = here.glob("*_rite_of_settling_service_path.py")
    spec = spec_from_file_location("rite_of_settling_service_path_migration", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load_migration()
OTHER_PATH = "world.magic.services.placeholder_ritual"


class _Apps:
    """Stands in for the migration's ``apps`` registry: ``get_model`` answers the plain base
    manager, as a historical model would."""

    @staticmethod
    def get_model(app_label: str, model_name: str) -> SimpleNamespace:
        assert (app_label, model_name) == ("arxii", "Ritual")
        return SimpleNamespace(objects=Ritual._base_manager)


class RiteOfSettlingServicePathMigrationTests(TestCase):
    def ritual(self, name: str, path: str) -> int:
        return Ritual.objects.create(
            name=name, execution_kind=RitualExecutionKind.SERVICE, service_function_path=path
        ).pk

    @staticmethod
    def path_of(pk: int) -> str:
        return Ritual._base_manager.values_list("service_function_path", flat=True).get(pk=pk)

    def test_every_row_holding_the_old_path_takes_the_new_one_and_no_other_row_moves(self) -> None:
        old_a = self.ritual("Old A", MIGRATION.OLD_PATH)
        old_b = self.ritual("Old B", MIGRATION.OLD_PATH)
        other = self.ritual("Other", OTHER_PATH)

        MIGRATION.to_settling_rite(_Apps, None)

        self.assertEqual(self.path_of(old_a), MIGRATION.NEW_PATH)
        self.assertEqual(self.path_of(old_b), MIGRATION.NEW_PATH)
        self.assertEqual(self.path_of(other), OTHER_PATH)

    def test_running_it_again_or_with_no_match_changes_nothing(self) -> None:
        done = self.ritual("Done", MIGRATION.NEW_PATH)

        MIGRATION.to_settling_rite(_Apps, None)
        MIGRATION.to_settling_rite(_Apps, None)

        self.assertEqual(self.path_of(done), MIGRATION.NEW_PATH)

    def test_it_changes_nothing_on_an_empty_database(self) -> None:
        MIGRATION.to_settling_rite(_Apps, None)

        self.assertFalse(Ritual._base_manager.exists())

    def test_reversing_restores_the_old_path(self) -> None:
        ritual = self.ritual("Settled", MIGRATION.NEW_PATH)

        MIGRATION.to_drift_correction_rite(_Apps, None)

        self.assertEqual(self.path_of(ritual), MIGRATION.OLD_PATH)
