"""species.sun_reconcile cron task (#2846)."""

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.models import CharacterDistinction
from world.game_clock.task_registry import get_registered_tasks
from world.species.factories import ensure_sunlight_distinctions
from world.species.tasks import register_all_tasks, sun_reconcile_tick


class SunReconcileTaskTest(TestCase):
    def test_registers_with_game_clock(self):
        register_all_tasks()
        keys = {t.task_key for t in get_registered_tasks()}
        self.assertIn("species.sun_reconcile", keys)

    def test_sweeps_distinction_holders(self):
        """A stationary sun-sensitive character is reconciled without moving."""
        bane, _allergy = ensure_sunlight_distinctions()
        sheet = CharacterSheetFactory()
        CharacterDistinction.objects.create(character=sheet, distinction=bane)
        with patch("world.species.services.reconcile_sunlight_exposure") as reconcile:
            sun_reconcile_tick()
        reconcile.assert_called_once_with(sheet.character, sheet.character.location)

    def test_sweep_survives_a_failing_row(self):
        """One broken character never aborts the sweep."""
        bane, allergy = ensure_sunlight_distinctions()
        sheet_a = CharacterSheetFactory()
        sheet_b = CharacterSheetFactory()
        CharacterDistinction.objects.create(character=sheet_a, distinction=bane)
        CharacterDistinction.objects.create(character=sheet_b, distinction=allergy)
        with patch(
            "world.species.services.reconcile_sunlight_exposure",
            side_effect=[RuntimeError("boom"), None],
        ) as reconcile:
            sun_reconcile_tick()
        self.assertEqual(reconcile.call_count, 2)
