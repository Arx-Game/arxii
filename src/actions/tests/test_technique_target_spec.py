"""Tests for the technique branch of _target_spec_for_action.

Verifies:
- A SINGLE-cardinality enemy (hostile) technique → target_spec.cardinality == "single",
  filters.exclude_self == True.
- An AREA ally technique → cardinality == "area", exclude_self == True (ALLY excludes self
  same as ENEMY for picker purposes).
- A SELF target_type technique → target_spec is None (self-actions carry no spec).
"""

from __future__ import annotations

import django.test

from actions.constants import ActionBackend, ActionTargetType
from actions.types import TargetType
from world.combat.constants import EncounterStatus, ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory


class TechniqueTargetSpecTests(django.test.TestCase):
    """COMBAT PlayerActions for technique declarations carry correct target_spec."""

    @classmethod
    def setUpTestData(cls) -> None:
        from actions.factories import ActionTemplateFactory
        from world.checks.factories import CheckTypeFactory
        from world.magic.factories import (
            BinaryEffectTypeFactory,
            CharacterTechniqueFactory,
            TechniqueAppliedConditionFactory,
            TechniqueFactory,
        )
        from world.magic.models.techniques import ConditionTargetKind

        cls.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            status=ParticipantStatus.ACTIVE,
        )
        cls.sheet = cls.participant.character_sheet
        cls.character = cls.sheet.character

        check_type = CheckTypeFactory()

        # --- enemy SINGLE technique (hostile → derive_target_relationship = ENEMY) ---
        template_enemy = ActionTemplateFactory(check_type=check_type)
        cls.enemy_single_technique = TechniqueFactory(
            damage_profile=True,  # hostile
            action_template=template_enemy,
            target_type=ActionTargetType.SINGLE,
        )
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.enemy_single_technique)

        # --- ally AREA technique (non-hostile with ALLY condition) ---
        template_ally = ActionTemplateFactory(check_type=check_type)
        cls.ally_area_technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=template_ally,
            target_type=ActionTargetType.AREA,
        )
        TechniqueAppliedConditionFactory(
            technique=cls.ally_area_technique,
            target_kind=ConditionTargetKind.ALLY,
        )
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.ally_area_technique)

        # --- self target_type technique (SELF cardinality → spec should be None) ---
        template_self = ActionTemplateFactory(check_type=check_type)
        cls.self_technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=template_self,
            target_type=ActionTargetType.SELF,
        )
        TechniqueAppliedConditionFactory(
            technique=cls.self_technique,
            target_kind=ConditionTargetKind.SELF,
        )
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.self_technique)

    def _get_combat_action_for_technique(self, technique_id: int):
        """Return the COMBAT PlayerAction for a specific technique_id, or None."""
        from actions.player_interface import get_player_actions

        actions = get_player_actions(self.character)
        for action in actions:
            if action.backend == ActionBackend.COMBAT and action.ref.technique_id == technique_id:
                return action
        return None

    def test_enemy_single_technique_target_spec_cardinality(self) -> None:
        """SINGLE-cardinality hostile technique → target_spec.cardinality == 'single'."""
        action = self._get_combat_action_for_technique(self.enemy_single_technique.pk)
        self.assertIsNotNone(action, "Expected COMBAT action for enemy single technique")
        self.assertIsNotNone(action.target_spec)
        self.assertEqual(action.target_spec.cardinality, TargetType.SINGLE)

    def test_enemy_single_technique_target_spec_exclude_self(self) -> None:
        """SINGLE-cardinality hostile technique → filters.exclude_self == True."""
        action = self._get_combat_action_for_technique(self.enemy_single_technique.pk)
        self.assertIsNotNone(action, "Expected COMBAT action for enemy single technique")
        self.assertIsNotNone(action.target_spec)
        self.assertTrue(action.target_spec.filters.exclude_self)

    def test_enemy_single_technique_target_spec_in_same_scene(self) -> None:
        """SINGLE-cardinality hostile technique → filters.in_same_scene == True."""
        action = self._get_combat_action_for_technique(self.enemy_single_technique.pk)
        self.assertIsNotNone(action)
        self.assertIsNotNone(action.target_spec)
        self.assertTrue(action.target_spec.filters.in_same_scene)

    def test_ally_area_technique_target_spec_cardinality(self) -> None:
        """AREA ally technique → target_spec.cardinality == 'area'."""
        action = self._get_combat_action_for_technique(self.ally_area_technique.pk)
        self.assertIsNotNone(action, "Expected COMBAT action for ally area technique")
        self.assertIsNotNone(action.target_spec)
        self.assertEqual(action.target_spec.cardinality, TargetType.AREA)

    def test_ally_area_technique_target_spec_exclude_self(self) -> None:
        """AREA ally technique → filters.exclude_self == True (ALLY excludes self)."""
        action = self._get_combat_action_for_technique(self.ally_area_technique.pk)
        self.assertIsNotNone(action, "Expected COMBAT action for ally area technique")
        self.assertIsNotNone(action.target_spec)
        self.assertTrue(action.target_spec.filters.exclude_self)

    def test_self_target_type_technique_target_spec_is_none(self) -> None:
        """A technique with target_type=SELF → target_spec is None (self-action)."""
        action = self._get_combat_action_for_technique(self.self_technique.pk)
        self.assertIsNotNone(action, "Expected COMBAT action for self technique")
        self.assertIsNone(action.target_spec)
