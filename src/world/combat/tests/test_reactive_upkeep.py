"""Tests for drain_reactive_upkeep — per-round anima drain for sustained conditions.

The drain fires at the top of resolve_round (Task 5 / #1584).  Conditions with
``upkeep_anima_per_round > 0`` are sustained by debiting the bearer's anima each
round; an unaffordable condition lapses (its ConditionInstance row is deleted).
"""

from unittest.mock import patch

from django.test import TestCase, tag

from world.combat.constants import RiskLevel
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.services import drain_reactive_upkeep
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.magic.factories import CharacterAnimaFactory


@tag("postgres")
class ReactiveUpkeepTests(TestCase):
    def _setup(self, anima_current: int, upkeep: int, consented: bool = False) -> tuple:
        # LETHAL so the consented-deficit test exercises the life-force-drawing
        # path by default (mirrors _build_guardian_and_ally in
        # test_guardian_reactions.py, #3573); unconsented paths never read
        # is_lethal (they lapse via a plain compare, not deduct_anima).
        enc = CombatEncounterFactory(risk_level=RiskLevel.LETHAL)
        part = CombatParticipantFactory(encounter=enc)
        char = part.character_sheet.character
        CharacterAnimaFactory(character=char.sheet_data, current=anima_current, maximum=20)
        tmpl = ConditionTemplateFactory(upkeep_anima_per_round=upkeep)
        inst = ConditionInstanceFactory(condition=tmpl, target=char, soulfray_consented=consented)
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

    def test_consented_upkeep_holds_through_deficit_and_accrues(self) -> None:
        enc, char, inst = self._setup(anima_current=1, upkeep=3, consented=True)
        with (
            patch("world.combat.services.accumulate_soulfray") as accrue,
            patch("world.combat.services._broadcast_commitment_line") as line,
        ):
            drain_reactive_upkeep(enc)
        self.assertTrue(type(inst).objects.filter(pk=inst.pk).exists())
        char.anima.refresh_from_db()
        self.assertEqual(char.anima.current, 0)
        self.assertEqual(accrue.call_args.kwargs["deficit"], 2)
        self.assertIn("bleeds soul", line.call_args.args[1])

    def test_unconsented_upkeep_still_lapses(self) -> None:
        enc, _char, inst = self._setup(anima_current=1, upkeep=3)
        drain_reactive_upkeep(enc)
        self.assertFalse(type(inst).objects.filter(pk=inst.pk).exists())
