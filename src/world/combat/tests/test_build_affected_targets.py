"""Tests for _build_affected_targets helper."""

from evennia.utils.test_resources import EvenniaTestCase


class BuildAffectedTargetsTests(EvenniaTestCase):
    def test_opponent_target_resolves_to_objectdb(self):
        from world.combat.factories import (
            CombatOpponentFactory,
            CombatRoundActionFactory,
        )
        from world.combat.services import _build_affected_targets

        opp = CombatOpponentFactory()
        action = CombatRoundActionFactory(focused_opponent_target=opp)
        targets = _build_affected_targets(action.participant, action)
        self.assertEqual(targets, [opp.objectdb])

    def test_ally_target_resolves_to_character(self):
        from world.combat.factories import (
            CombatParticipantFactory,
            CombatRoundActionFactory,
        )
        from world.combat.services import _build_affected_targets

        ally = CombatParticipantFactory()
        action = CombatRoundActionFactory(focused_ally_target=ally)
        targets = _build_affected_targets(action.participant, action)
        self.assertEqual(targets, [ally.character_sheet.character])

    def test_no_target_returns_empty_list(self):
        from world.combat.factories import CombatRoundActionFactory
        from world.combat.services import _build_affected_targets

        action = CombatRoundActionFactory()
        targets = _build_affected_targets(action.participant, action)
        self.assertEqual(targets, [])
