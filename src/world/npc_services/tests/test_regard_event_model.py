"""Tests for NpcRegardEvent's citation-matrix validation (#2039)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.combat.factories import CombatOpponentActionFactory, CombatRoundActionFactory
from world.npc_services.constants import NpcRegardEventReason
from world.npc_services.factories import NpcRegardEventFactory, NpcRegardFactory
from world.scenes.factories import SceneFactory
from world.stories.factories import StakeResolutionFactory


class NpcRegardEventCitationTests(TestCase):
    def test_npc_harmed_pc_requires_a_citation(self):
        event = NpcRegardEventFactory.build(
            regard=NpcRegardFactory(),
            reason=NpcRegardEventReason.NPC_HARMED_PC_INTEREST,
            amount=-10,
        )
        with self.assertRaises(ValidationError):
            event.full_clean()

    def test_npc_harmed_pc_accepts_npc_combat_action_citation(self):
        event = NpcRegardEventFactory.build(
            regard=NpcRegardFactory(),
            reason=NpcRegardEventReason.NPC_HARMED_PC_INTEREST,
            amount=-10,
            source_npc_combat_action=CombatOpponentActionFactory(),
        )
        event.full_clean()  # does not raise

    def test_pc_foiled_npc_rejects_wrong_citation_type(self):
        event = NpcRegardEventFactory.build(
            regard=NpcRegardFactory(),
            reason=NpcRegardEventReason.PC_FOILED_NPC_PLAN,
            amount=-10,
            source_npc_combat_action=CombatOpponentActionFactory(),
        )
        with self.assertRaises(ValidationError):
            event.full_clean()

    def test_stake_resolution_requires_that_citation_only(self):
        event = NpcRegardEventFactory.build(
            regard=NpcRegardFactory(),
            reason=NpcRegardEventReason.STAKE_RESOLUTION,
            amount=5,
        )
        with self.assertRaises(ValidationError):
            event.full_clean()
        event.source_stake_resolution = StakeResolutionFactory()
        event.full_clean()  # does not raise

    def test_distinction_seed_rejects_any_citation(self):
        event = NpcRegardEventFactory.build(
            regard=NpcRegardFactory(),
            reason=NpcRegardEventReason.DISTINCTION_SEED,
            amount=5,
            source_stake_resolution=StakeResolutionFactory(),
        )
        with self.assertRaises(ValidationError):
            event.full_clean()

    def test_distinction_seed_accepts_no_citation(self):
        event = NpcRegardEventFactory.build(
            regard=NpcRegardFactory(),
            reason=NpcRegardEventReason.DISTINCTION_SEED,
            amount=5,
        )
        event.full_clean()  # does not raise

    def test_gm_manual_adjustment_allows_zero_or_one_citation(self):
        uncited = NpcRegardEventFactory.build(
            regard=NpcRegardFactory(),
            reason=NpcRegardEventReason.GM_MANUAL_ADJUSTMENT,
            amount=5,
        )
        uncited.full_clean()  # does not raise
        cited = NpcRegardEventFactory.build(
            regard=NpcRegardFactory(),
            reason=NpcRegardEventReason.GM_MANUAL_ADJUSTMENT,
            amount=5,
            source_pc_combat_action=CombatRoundActionFactory(),
        )
        cited.full_clean()  # does not raise

    def test_social_action_resolved_requires_scene_citation(self):
        event = NpcRegardEventFactory.build(
            regard=NpcRegardFactory(),
            reason=NpcRegardEventReason.SOCIAL_ACTION_RESOLVED,
            amount=5,
        )
        with self.assertRaises(ValidationError):
            event.full_clean()

    def test_social_action_resolved_accepts_scene_citation(self):
        event = NpcRegardEventFactory.build(
            regard=NpcRegardFactory(),
            reason=NpcRegardEventReason.SOCIAL_ACTION_RESOLVED,
            amount=5,
            source_scene=SceneFactory(),
        )
        event.full_clean()  # does not raise

    def test_pc_foiled_npc_accepts_pc_combat_action_citation(self):
        event = NpcRegardEventFactory.build(
            regard=NpcRegardFactory(),
            reason=NpcRegardEventReason.PC_FOILED_NPC_PLAN,
            amount=-10,
            source_pc_combat_action=CombatRoundActionFactory(),
        )
        event.full_clean()  # does not raise

    def test_gm_manual_adjustment_rejects_two_citations(self):
        event = NpcRegardEventFactory.build(
            regard=NpcRegardFactory(),
            reason=NpcRegardEventReason.GM_MANUAL_ADJUSTMENT,
            amount=5,
            source_pc_combat_action=CombatRoundActionFactory(),
            source_npc_combat_action=CombatOpponentActionFactory(),
        )
        with self.assertRaises(ValidationError):
            event.full_clean()
