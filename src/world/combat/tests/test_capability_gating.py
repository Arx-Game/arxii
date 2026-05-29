"""Tests for combat eligibility via the capability/agency model (Task 7 / #595).

Combat eligibility no longer keys on CharacterVitals.status / dying_final_round.
It now keys on:
- can_act(character): not dead AND has awareness > 0 (the coarse round-participation gate).
- technique_performable(character, technique): per-technique capability requirements.

Tiering:
- Unconscious is a non-progressive condition → apply_condition avoids the PG-only
  DISTINCT ON path, so Unconscious-only tests run on SQLite.
- Bleeding-Out is progressive → apply_condition hits DISTINCT ON → needs PG.
  Those tests carry @tag("postgres").
"""

from django.test import TestCase, tag

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ActionCategory, EncounterStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import declare_action
from world.conditions.constants import (
    BLEED_OUT_CONDITION_NAME,
    FoundationalCapability,
)
from world.conditions.factories import (
    BleedingOutConditionFactory,
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionStageFactory,
    UnconsciousConditionFactory,
)
from world.conditions.services import apply_condition
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.vitals.constants import CharacterLifeState
from world.vitals.models import CharacterVitals
from world.vitals.services import can_act


def _awareness_capability():
    """Get-or-create the foundational AWARENESS capability with innate_baseline=1."""
    return CapabilityTypeFactory(name=FoundationalCapability.AWARENESS, innate_baseline=1)


def _make_unconscious_condition():
    """Build an Unconscious condition that zeroes the AWARENESS capability."""
    awareness = _awareness_capability()
    condition = UnconsciousConditionFactory()
    ConditionCapabilityEffectFactory(
        condition=condition,
        capability=awareness,
        value=-100,
    )
    return condition


def _make_declaring_encounter_with_participant():
    """Create a DECLARING encounter, a participant with ALIVE vitals, and one opponent."""
    encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
    participant = CombatParticipantFactory(encounter=encounter)
    CharacterVitals.objects.create(
        character_sheet=participant.character_sheet,
        health=100,
        max_health=100,
        base_max_health=100,
        life_state=CharacterLifeState.ALIVE,
    )
    opponent = CombatOpponentFactory(encounter=encounter)
    return encounter, participant, opponent


class CanActTests(TestCase):
    """Direct unit tests of can_act."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.vitals = CharacterVitals.objects.create(
            character_sheet=cls.sheet,
            health=100,
            max_health=100,
            base_max_health=100,
            life_state=CharacterLifeState.ALIVE,
        )

    def test_alive_and_aware_can_act(self) -> None:
        """ALIVE + awareness baseline 1, no impairment → can_act True."""
        _awareness_capability()
        self.assertTrue(can_act(self.character))

    def test_awareness_unseeded_can_act(self) -> None:
        """No AWARENESS capability seeded at all → graceful True (no blocking)."""
        self.assertTrue(can_act(self.character))

    def test_dead_cannot_act(self) -> None:
        """life_state=DEAD → can_act False regardless of awareness."""
        _awareness_capability()
        self.vitals.life_state = CharacterLifeState.DEAD
        self.vitals.save(update_fields=["life_state"])
        self.assertFalse(can_act(self.character))

    def test_awareness_zeroed_cannot_act(self) -> None:
        """Unconscious zeroes awareness → can_act False even though not dead."""
        condition = _make_unconscious_condition()
        apply_condition(target=self.character, condition=condition)
        self.assertFalse(can_act(self.character))


class DeclareActionCapabilityGatingTests(TestCase):
    """declare_action eligibility now gates on can_act, not vitals.status."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_type_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.gift = GiftFactory()

    def test_unconscious_character_cannot_declare(self) -> None:
        """An Unconscious (awareness=0) participant cannot declare an action."""
        _, participant, opponent = _make_declaring_encounter_with_participant()
        condition = _make_unconscious_condition()
        apply_condition(target=participant.character_sheet.character, condition=condition)

        technique = TechniqueFactory(gift=self.gift, effect_type=self.effect_type_attack)
        with self.assertRaisesRegex(ValueError, "dead or incapacitated"):
            declare_action(
                participant,
                focused_action=technique,
                focused_category=ActionCategory.PHYSICAL,
                effort_level=EffortLevel.MEDIUM,
                focused_opponent_target=opponent,
            )

    def test_conscious_character_can_declare(self) -> None:
        """An ALIVE + aware participant declares normally (sanity baseline)."""
        _awareness_capability()
        _, participant, opponent = _make_declaring_encounter_with_participant()

        technique = TechniqueFactory(gift=self.gift, effect_type=self.effect_type_attack)
        action = declare_action(
            participant,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=opponent,
        )
        self.assertEqual(action.focused_action_id, technique.pk)


@tag("postgres")
class DeclareActionDyingTests(TestCase):
    """A dying-but-conscious character (Bleeding-Out, awareness intact) can still declare.

    Bleeding-Out is progressive → apply_condition uses PG DISTINCT ON → @tag('postgres').
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_type_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.gift = GiftFactory()

    def test_dying_conscious_character_can_declare(self) -> None:
        """Bleeding-Out does NOT impair awareness → can_act True → declaration succeeds."""
        _awareness_capability()
        _, participant, opponent = _make_declaring_encounter_with_participant()

        bleed_out = BleedingOutConditionFactory()
        # Entry stage so apply_condition can set current_stage on a progressive template.
        ConditionStageFactory(
            condition=bleed_out,
            stage_order=1,
            name="Bleeding",
            rounds_to_next=None,
        )
        result = apply_condition(
            target=participant.character_sheet.character,
            condition=bleed_out,
        )
        self.assertTrue(result.success)
        self.assertEqual(bleed_out.name, BLEED_OUT_CONDITION_NAME)

        technique = TechniqueFactory(gift=self.gift, effect_type=self.effect_type_attack)
        action = declare_action(
            participant,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=opponent,
        )
        self.assertEqual(action.focused_action_id, technique.pk)
