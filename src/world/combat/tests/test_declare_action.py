"""Tests for declare_action target validation."""

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ActionCategory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.round_context import CombatRoundContext
from world.combat.services import declare_action
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    EffectTypeFactory,
    FuryTierFactory,
    GiftFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
)
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


def _make_encounter_and_participant() -> tuple:
    """Helper: create DECLARING encounter, participant with ALIVE vitals, and one opponent."""
    encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
    participant = CombatParticipantFactory(encounter=encounter)
    CharacterVitals.objects.create(
        character_sheet=participant.character_sheet, health=100, max_health=100
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
            character_sheet=self.ally_participant.character_sheet, health=100, max_health=100
        )

    def test_focused_category_derived_from_technique(self) -> None:
        """focused_category comes from the technique, overriding the client value (#614)."""
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_type_buff,
            action_category=ActionCategory.MENTAL,
        )
        TechniqueAppliedConditionFactory(technique=technique, target_kind="ally")
        action = declare_action(
            self.participant,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,  # client value — overridden by the technique
            effort_level=EffortLevel.MEDIUM,
            focused_ally_target=self.ally_participant,
        )
        self.assertEqual(action.focused_category, ActionCategory.MENTAL)

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


class DeclareActionSoulFrayFuryFieldsTests(TestCase):
    """declare_action persists confirm_soulfray_risk, fury_commitment, fury_anchor (Task 2, #1454).

    Tests two levels:
    1. Direct declare_action call — verifies the service persists the fields.
    2. Full round-declaration path (round_declaration → ctx.record_declaration →
       _record_combat_declaration → declare_action) — verifies the id-forwarding
       chain in CastTechniqueAction and _record_combat_declaration.
    """

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        _, self.participant, _ = _make_encounter_and_participant()
        self.fury_tier = FuryTierFactory()
        self.anchor_sheet = CharacterSheetFactory()

    def test_declare_action_persists_confirm_soulfray_risk(self) -> None:
        """confirm_soulfray_risk=True is stored on the CombatRoundAction row."""
        action = declare_action(
            self.participant,
            effort_level=EffortLevel.MEDIUM,
            confirm_soulfray_risk=True,
        )
        self.assertTrue(action.confirm_soulfray_risk)

    def test_declare_action_persists_fury_commitment(self) -> None:
        """fury_commitment FK is stored on the CombatRoundAction row."""
        action = declare_action(
            self.participant,
            effort_level=EffortLevel.MEDIUM,
            fury_commitment=self.fury_tier,
        )
        self.assertEqual(action.fury_commitment, self.fury_tier)

    def test_declare_action_persists_fury_anchor(self) -> None:
        """fury_anchor FK is stored on the CombatRoundAction row."""
        action = declare_action(
            self.participant,
            effort_level=EffortLevel.MEDIUM,
            fury_anchor=self.anchor_sheet,
        )
        self.assertEqual(action.fury_anchor, self.anchor_sheet)

    def test_declare_action_persists_all_three_fields_together(self) -> None:
        """All three soulfray/fury fields are persisted together on one row."""
        action = declare_action(
            self.participant,
            effort_level=EffortLevel.MEDIUM,
            confirm_soulfray_risk=True,
            fury_commitment=self.fury_tier,
            fury_anchor=self.anchor_sheet,
        )
        self.assertTrue(action.confirm_soulfray_risk)
        self.assertEqual(action.fury_commitment, self.fury_tier)
        self.assertEqual(action.fury_anchor, self.anchor_sheet)

    def test_full_declaration_path_threads_soulfray_fury_fields(self) -> None:
        """Full path: round_declaration → ctx.record_declaration persists soulfray/fury.

        CastTechniqueAction.round_declaration forwards confirm_soulfray_risk +
        fury_commitment_id + fury_anchor_id into decl_kwargs; _record_combat_declaration
        resolves those ids and passes instances to declare_action.
        """
        from actions.definitions.cast import CastTechniqueAction

        gift = GiftFactory()
        effect_type = EffectTypeFactory(name="Buff_fury", base_power=None)
        technique = TechniqueFactory(gift=gift, effect_type=effect_type)
        TechniqueAppliedConditionFactory(technique=technique, target_kind="self")

        ctx = CombatRoundContext(self.participant)
        action = CastTechniqueAction()

        # round_declaration returns (PlayerAction, decl_kwargs) with the ids forwarded.
        result = action.round_declaration(
            ctx,
            technique_id=technique.pk,
            effort_level=EffortLevel.MEDIUM,
            confirm_soulfray_risk=True,
            fury_commitment_id=self.fury_tier.pk,
            fury_anchor_id=self.anchor_sheet.pk,
        )
        self.assertIsNotNone(result, "round_declaration must return a tuple in CombatRoundContext.")
        pa, decl_kwargs = result

        # Verify the ids were forwarded into decl_kwargs.
        self.assertTrue(decl_kwargs.get("confirm_soulfray_risk"))
        self.assertEqual(decl_kwargs.get("fury_commitment_id"), self.fury_tier.pk)
        self.assertEqual(decl_kwargs.get("fury_anchor_id"), self.anchor_sheet.pk)

        # Now exercise _record_combat_declaration via record_declaration.
        ctx.record_declaration(self.participant.character_sheet, pa, decl_kwargs)

        # The persisted CombatRoundAction must carry all three fields.
        round_action = CombatRoundAction.objects.get(
            participant=self.participant,
            round_number=self.participant.encounter.round_number,
        )
        self.assertTrue(round_action.confirm_soulfray_risk)
        self.assertEqual(round_action.fury_commitment, self.fury_tier)
        self.assertEqual(round_action.fury_anchor, self.anchor_sheet)
