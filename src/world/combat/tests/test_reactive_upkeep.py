"""Tests for drain_reactive_upkeep — per-round anima drain for sustained conditions.

The drain fires at the top of resolve_round (Task 5 / #1584).  Conditions with
``upkeep_anima_per_round > 0`` are sustained by debiting the bearer's anima each
round; an unaffordable condition lapses (its ConditionInstance row is deleted).
"""

from django.test import TestCase, tag

from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.services import drain_reactive_upkeep
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.magic.factories import CharacterAnimaFactory


@tag("postgres")
class ReactiveUpkeepTests(TestCase):
    def _setup(self, anima_current: int, upkeep: int) -> tuple:
        enc = CombatEncounterFactory()
        part = CombatParticipantFactory(encounter=enc)
        char = part.character_sheet.character
        CharacterAnimaFactory(character=char, current=anima_current, maximum=20)
        tmpl = ConditionTemplateFactory(upkeep_anima_per_round=upkeep)
        inst = ConditionInstanceFactory(condition=tmpl, target=char)
        return enc, char, inst

    def test_upkeep_debits_anima(self) -> None:
        """Affordable upkeep deducts anima and keeps the condition alive."""
        enc, char, inst = self._setup(anima_current=10, upkeep=3)
        drain_reactive_upkeep(enc)
        char.anima.refresh_from_db()
        self.assertEqual(char.anima.current, 7)
        self.assertTrue(type(inst).objects.filter(pk=inst.pk).exists())

    def test_unaffordable_upkeep_lapses_condition(self) -> None:
        """Unaffordable upkeep deletes the ConditionInstance (condition lapses)."""
        enc, _char, inst = self._setup(anima_current=1, upkeep=3)
        drain_reactive_upkeep(enc)
        self.assertFalse(type(inst).objects.filter(pk=inst.pk).exists())
