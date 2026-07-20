"""Tests for _resolve_primary_target_sheet — the target threading fix for
per-vow situational perks (#2536, Task 4 review fix). Mirrors
test_build_affected_targets.py's structure for the sibling helper."""

from evennia.utils.test_resources import EvenniaTestCase


class ResolvePrimaryTargetSheetTests(EvenniaTestCase):
    def test_ally_target_resolves_to_character_sheet(self):
        from world.combat.factories import (
            CombatParticipantFactory,
            CombatRoundActionFactory,
        )
        from world.combat.services import _resolve_primary_target_sheet

        ally = CombatParticipantFactory()
        action = CombatRoundActionFactory(focused_ally_target=ally)
        self.assertEqual(_resolve_primary_target_sheet(action), ally.character_sheet)

    def test_persona_backed_opponent_resolves_to_character_sheet(self):
        """A 'story NPC' opponent (persona set) resolves to the persona's own
        CharacterSheet — the seam that lets target-keyed situational perks fire
        against a persistent NPC identity."""
        from world.combat.factories import CombatOpponentFactory, CombatRoundActionFactory
        from world.combat.services import _resolve_primary_target_sheet
        from world.scenes.factories import PersonaFactory

        persona = PersonaFactory()
        opponent = CombatOpponentFactory(persona=persona)
        action = CombatRoundActionFactory(focused_opponent_target=opponent)
        self.assertEqual(_resolve_primary_target_sheet(action), persona.character_sheet)

    def test_bare_npc_opponent_resolves_to_none(self):
        """A bare (non-persona) NPC opponent has no CharacterSheet -> None,
        exactly like a targetless cast; target-keyed situations correctly
        never hold against it."""
        from world.combat.factories import CombatOpponentFactory, CombatRoundActionFactory
        from world.combat.services import _resolve_primary_target_sheet

        opponent = CombatOpponentFactory()
        action = CombatRoundActionFactory(focused_opponent_target=opponent)
        self.assertIsNone(_resolve_primary_target_sheet(action))

    def test_no_target_resolves_to_none(self):
        from world.combat.factories import CombatRoundActionFactory
        from world.combat.services import _resolve_primary_target_sheet

        action = CombatRoundActionFactory()
        self.assertIsNone(_resolve_primary_target_sheet(action))
