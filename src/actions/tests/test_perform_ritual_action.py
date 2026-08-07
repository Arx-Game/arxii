"""Tests for PerformRitualAction CEREMONY branch.

The happy-path ceremony (creates PendingRitualEffect) is covered by the E2E
journey tests ``test_ritual_telnet_e2e.py`` and ``test_weave_imbue_pull_journey_e2e.py``
(Step 1). This test retains only the edge case the journey does NOT cover:
attempting a ceremony when one is already in progress.
"""

from django.test import TestCase

from actions.definitions.ritual import PerformRitualAction
from world.magic.constants import RitualExecutionKind
from world.magic.factories import CharacterAuraFactory, CharacterResonanceFactory, RitualFactory
from world.magic.models import PendingRitualEffect


class PerformRitualActionCeremonyTests(TestCase):
    def setUp(self):
        self.cr = CharacterResonanceFactory()
        self.sheet = self.cr.character_sheet
        self.character = self.sheet.character
        CharacterAuraFactory(character=self.sheet)  # Gifted: hedge gate (#3001)
        self.ritual = RitualFactory(
            name="Rite of Weaving",
            execution_kind=RitualExecutionKind.CEREMONY,
            service_function_path="",
        )

    def test_ceremony_already_in_progress_fails(self):
        PendingRitualEffect.objects.create(character=self.sheet, ritual=self.ritual)
        action = PerformRitualAction()
        result = action.run(self.character, ritual=self.ritual)
        self.assertFalse(result.success)
        self.assertIn("already in progress", result.message)


class PerformRitualActionPoolGateTests(TestCase):
    """#3001: a solo perform auto-channels toward the anima requirement and gates."""

    def setUp(self):
        from world.magic.models.anima import CharacterAnima

        self.cr = CharacterResonanceFactory()
        self.sheet = self.cr.character_sheet
        self.character = self.sheet.character
        CharacterAuraFactory(character=self.sheet)  # Gifted: hedge gate (#3001)
        self.anima, _ = CharacterAnima.objects.update_or_create(
            character=self.sheet, defaults={"current": 50, "maximum": 100}
        )
        self.ritual = RitualFactory(
            name="Costly Rite",
            execution_kind=RitualExecutionKind.CEREMONY,
            service_function_path="",
            anima_requirement=30,
        )

    def test_solo_perform_channels_the_requirement(self):
        from world.magic.models.ritual_pool import RitualAnimaContribution

        action = PerformRitualAction()
        result = action.run(self.character, ritual=self.ritual)
        self.assertTrue(result.success)
        self.assertFalse(result.data["spectacular"])
        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 20)
        row = RitualAnimaContribution.objects.get()
        self.assertEqual(row.amount, 30)
        self.assertIsNone(row.session_id)

    def test_solo_perform_fizzles_on_deficit_without_check_config(self):
        self.anima.current = 5
        self.anima.save(update_fields=["current"])
        action = PerformRitualAction()
        result = action.run(self.character, ritual=self.ritual)
        self.assertFalse(result.success)
        self.assertIn("gutters", result.message)
        # The pool was still consumed — the rite happened, and it died.
        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 0)

    def test_solo_perform_with_no_anima_at_all_fails_clean(self):
        self.anima.current = 0
        self.anima.save(update_fields=["current"])
        action = PerformRitualAction()
        result = action.run(self.character, ritual=self.ritual)
        self.assertFalse(result.success)
        # Subclass raises keep the curated class-level user_message (#2386).
        self.assertIn("contribute", result.message.lower())
