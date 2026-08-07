"""E2E: PerformRitualAction defers a ritual across combat rounds (#2705, Task 5).

Companion to ``test_perform_ritual_action_touchstone.py`` (component
consumption) and ``actions/tests/test_perform_ritual_action.py`` (bare
CEREMONY dispatch) — those two prove the pre-Task-5 shape is unchanged
(``dispatch_ritual``'s extraction is behaviour-preserving). This module
covers what's new: ``PerformRitualAction.execute()`` consulting
``try_declare_sustained_ritual`` between component consumption and dispatch,
and the maturation-time "broken commitment stays spent" guarantee for a
ritual's already-consumed components.

Uses CEREMONY dispatch throughout (as the touchstone test does) — zero
dependency on an unbuilt SERVICE target, and it exercises the exact
``_validate_components`` -> deferral-check -> dispatch ordering this task
rewires either way.
"""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.ritual import PerformRitualAction
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.combat.constants import CONCENTRATION_CHECK_TYPE_NAME, ParticipantStatus, SustainedKind
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import SustainedAction
from world.combat.services import _mature_one_sustained_action
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.magic.constants import RitualExecutionKind
from world.magic.factories import (
    CharacterAuraFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    ResonanceTierFactory,
    RitualCheckConfigFactory,
    RitualComponentRequirementFactory,
    RitualFactory,
)
from world.magic.models import PendingRitualEffect
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


def _make_ceremony_ritual(*, sustained_rounds: int):
    ritual = RitualFactory(
        execution_kind=RitualExecutionKind.CEREMONY,
        service_function_path="",
    )
    RitualCheckConfigFactory(ritual=ritual, sustained_rounds=sustained_rounds)
    return ritual


class PerformRitualActionSustainedDeferralTests(TestCase):
    """No components involved — proves the deferral gate + inertness cases."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Concentration is authored ONLY in the lore repo (see
        # test_sustained_declaration.py) — built here with factories since
        # the fire-path test rolls it via roll_sustained_absorption_budget.
        cls.concentration_category = CheckCategoryFactory(
            name="perform-ritual-sustained-composure-checks"
        )
        cls.concentration_check_type = CheckTypeFactory(
            name=CONCENTRATION_CHECK_TYPE_NAME, category=cls.concentration_category
        )

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        CharacterAuraFactory(character=self.sheet)  # Gifted: hedge gate (#3001)
        self.character = self.sheet.character

    def _make_declaring_participant(self):
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        participant = CombatParticipantFactory(
            encounter=encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )
        CharacterVitals.objects.create(character_sheet=self.sheet, health=100, max_health=100)
        return participant

    def test_sustained_ritual_inside_declaring_encounter_defers(self) -> None:
        self._make_declaring_participant()
        ritual = _make_ceremony_ritual(sustained_rounds=2)

        action = PerformRitualAction()
        result = action.execute(self.character, ritual=ritual, components_provided=[])

        self.assertTrue(result.success)
        self.assertIn("holding it together", result.message)
        self.assertEqual(SustainedAction.objects.count(), 1)
        sustained = SustainedAction.objects.get()
        self.assertEqual(sustained.sustained_kind, SustainedKind.RITUAL)
        self.assertEqual(sustained.ritual_id, ritual.pk)
        # Deferred: dispatch never ran, so no PendingRitualEffect exists yet.
        self.assertFalse(PendingRitualEffect.objects.filter(ritual=ritual).exists())

    def test_outside_encounter_dispatches_immediately(self) -> None:
        """No CombatParticipant at all — the ordinary non-combat performance path."""
        ritual = _make_ceremony_ritual(sustained_rounds=2)

        action = PerformRitualAction()
        result = action.execute(self.character, ritual=ritual, components_provided=[])

        self.assertTrue(result.success)
        self.assertNotIn("holding it together", result.message)
        self.assertEqual(SustainedAction.objects.count(), 0)
        self.assertTrue(PendingRitualEffect.objects.filter(ritual=ritual).exists())

    def test_sustained_rounds_zero_dispatches_immediately(self) -> None:
        self._make_declaring_participant()
        ritual = _make_ceremony_ritual(sustained_rounds=0)

        action = PerformRitualAction()
        result = action.execute(self.character, ritual=ritual, components_provided=[])

        self.assertTrue(result.success)
        self.assertNotIn("holding it together", result.message)
        self.assertEqual(SustainedAction.objects.count(), 0)
        self.assertTrue(PendingRitualEffect.objects.filter(ritual=ritual).exists())

    def test_non_empty_kwargs_dispatches_immediately(self) -> None:
        """ADR-0007 guard: extra ritual kwargs make deferral impossible."""
        self._make_declaring_participant()
        ritual = _make_ceremony_ritual(sustained_rounds=2)

        action = PerformRitualAction()
        result = action.execute(
            self.character, ritual=ritual, components_provided=[], thread="some-target"
        )

        self.assertTrue(result.success)
        self.assertNotIn("holding it together", result.message)
        self.assertEqual(SustainedAction.objects.count(), 0)
        self.assertTrue(PendingRitualEffect.objects.filter(ritual=ritual).exists())


class PerformRitualActionSustainedComponentsSpentTests(TestCase):
    """Components are consumed at declaration; a broken sustain never refunds them."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.concentration_category = CheckCategoryFactory(
            name="perform-ritual-sustained-spent-composure-checks"
        )
        cls.concentration_check_type = CheckTypeFactory(
            name=CONCENTRATION_CHECK_TYPE_NAME, category=cls.concentration_category
        )

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        CharacterAuraFactory(character=self.sheet)  # Gifted: hedge gate (#3001)
        self.character = self.sheet.character
        self.resonance = ResonanceFactory(name="Praedari-Sustained")
        self.tier = ResonanceTierFactory(name="Faint-Sustained", tier_level=1)
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)
        self.ritual = _make_ceremony_ritual(sustained_rounds=2)
        RitualComponentRequirementFactory(
            ritual=self.ritual, item_template=None, min_touchstone_tier=self.tier
        )
        self.template = ItemTemplateFactory(tied_resonance=self.resonance, resonance_tier=self.tier)
        self.instance = ItemInstanceFactory(
            template=self.template, attuned_to_character_sheet=self.sheet
        )

        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        self.participant = CombatParticipantFactory(
            encounter=encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )
        CharacterVitals.objects.create(character_sheet=self.sheet, health=100, max_health=100)

    def test_component_consumed_at_declaration_and_stays_spent_when_broken(self) -> None:
        action = PerformRitualAction()
        result = action.execute(
            self.character, ritual=self.ritual, components_provided=[self.instance]
        )
        self.assertTrue(result.success)
        self.assertIn("holding it together", result.message)
        # The touchstone was consumed at declaration, not at (never-reached) dispatch.
        self.assertFalse(ItemInstance.objects.filter(pk=self.instance.pk).exists())

        sustained = SustainedAction.objects.get()
        # Force the break branch (downgrades >= budget) — dispatch never runs.
        sustained.downgrades = sustained.absorption_budget
        sustained.save(update_fields=["downgrades"])

        _mature_one_sustained_action(sustained, round_number=sustained.resolves_round)

        self.assertFalse(SustainedAction.objects.filter(pk=sustained.pk).exists())
        # Nothing restores the consumed component.
        self.assertFalse(ItemInstance.objects.filter(pk=self.instance.pk).exists())
