"""Tests for declare_action target validation."""

from django.test import TestCase

from world.combat.constants import ActionCategory, EncounterStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import declare_action
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    EffectTypeFactory,
    GiftFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
)
from world.vitals.constants import CharacterStatus
from world.vitals.models import CharacterVitals


def _make_encounter_and_participant() -> tuple:
    """Helper: create DECLARING encounter, participant with ALIVE vitals, and one opponent."""
    encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
    participant = CombatParticipantFactory(encounter=encounter)
    CharacterVitals.objects.create(
        character_sheet=participant.character_sheet,
        health=100,
        max_health=100,
        status=CharacterStatus.ALIVE,
    )
    opponent = CombatOpponentFactory(encounter=encounter)
    return encounter, participant, opponent


class DeclareActionTargetValidationTests(TestCase):
    """Tests for declare_action target validation: XOR, kind alignment, damage requires opponent."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_type_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.effect_type_buff = EffectTypeFactory(name="Buff", base_power=None)
        cls.gift = GiftFactory()

    def setUp(self) -> None:
        super().setUp()
        _, self.participant, self.opponent = _make_encounter_and_participant()
        # A second participant to act as an ally target
        encounter = self.participant.encounter
        self.ally_participant = CombatParticipantFactory(encounter=encounter)
        CharacterVitals.objects.create(
            character_sheet=self.ally_participant.character_sheet,
            health=100,
            max_health=100,
            status=CharacterStatus.ALIVE,
        )

    def test_xor_targets(self) -> None:
        """Providing both focused_opponent_target and focused_ally_target raises ValueError."""
        technique = TechniqueFactory(gift=self.gift, effect_type=self.effect_type_attack)
        with self.assertRaisesRegex(ValueError, "cannot target both"):
            declare_action(
                self.participant,
                focused_action=technique,
                focused_category=ActionCategory.PHYSICAL,
                effort_level=EffortLevel.MEDIUM,
                focused_opponent_target=self.opponent,
                focused_ally_target=self.ally_participant,
            )

    def test_target_kind_alignment_enemy_only(self) -> None:
        """Technique with only ENEMY condition rows + focused_ally_target raises ValueError."""
        technique = TechniqueFactory(gift=self.gift, effect_type=self.effect_type_buff)
        TechniqueAppliedConditionFactory(technique=technique, target_kind="enemy")
        with self.assertRaisesRegex(ValueError, "target_kinds"):
            declare_action(
                self.participant,
                focused_action=technique,
                focused_category=ActionCategory.PHYSICAL,
                effort_level=EffortLevel.MEDIUM,
                focused_ally_target=self.ally_participant,
            )

    def test_damage_only_requires_opponent_target(self) -> None:
        """Pure-damage technique (no condition rows) without opponent target → ValueError."""
        technique = TechniqueFactory(gift=self.gift, effect_type=self.effect_type_attack)
        # No condition rows: pure damage technique
        with self.assertRaisesRegex(ValueError, "Damage technique requires"):
            declare_action(
                self.participant,
                focused_action=technique,
                focused_category=ActionCategory.PHYSICAL,
                effort_level=EffortLevel.MEDIUM,
                # no focused_opponent_target provided
            )

    def test_buff_with_ally_target_kind_accepts_ally(self) -> None:
        """Technique with target_kind=ALLY rows + focused_ally_target succeeds."""
        technique = TechniqueFactory(gift=self.gift, effect_type=self.effect_type_buff)
        TechniqueAppliedConditionFactory(technique=technique, target_kind="ally")
        action = declare_action(
            self.participant,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_ally_target=self.ally_participant,
        )
        self.assertEqual(action.focused_ally_target, self.ally_participant)

    def test_buff_with_self_target_kind_accepts_self_via_ally_field(self) -> None:
        """Technique with target_kind=SELF rows + focused_ally_target=self succeeds."""
        technique = TechniqueFactory(gift=self.gift, effect_type=self.effect_type_buff)
        TechniqueAppliedConditionFactory(technique=technique, target_kind="self")
        action = declare_action(
            self.participant,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_ally_target=self.participant,
        )
        self.assertEqual(action.focused_ally_target, self.participant)

    def test_buff_with_ally_target_kind_accepts_self_via_ally_field(self) -> None:
        """ALLY-kind technique + focused_ally_target=self succeeds (SELF/ALLY interchangeable)."""
        technique = TechniqueFactory(gift=self.gift, effect_type=self.effect_type_buff)
        TechniqueAppliedConditionFactory(technique=technique, target_kind="ally")
        # Self passed via focused_ally_target — SELF/ALLY are interchangeable
        action = declare_action(
            self.participant,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_ally_target=self.participant,
        )
        self.assertEqual(action.focused_ally_target, self.participant)
