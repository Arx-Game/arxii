"""Waiting strike eligibility stays live as earlier strikes resolve."""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from world.combat.models import CombatEncounter, CombatOpponent, CombatOpponentMove
from world.combat.services.rounds.waiting_strikes import _eligible_waiters


class WaitingStrikeEligibilityTests(SimpleTestCase):
    def test_rechecks_each_npc_after_a_prior_strike(self):
        mover = CombatOpponent()
        first = CombatOpponentMove(opponent=CombatOpponent())
        second = CombatOpponentMove(opponent=CombatOpponent())
        eligible = {id(first): True, id(second): True}
        with (
            patch("world.combat.services.rounds.waiting_strikes._pc_waiters", return_value=[]),
            patch(
                "world.combat.services.rounds.waiting_strikes._npc_waiters",
                return_value=[first, second],
            ),
            patch(
                "world.combat.services.rounds.waiting_strikes._npc_waiter_eligible",
                side_effect=lambda row, _: eligible[id(row)],
            ),
        ):
            waiters = iter(_eligible_waiters(MagicMock(spec=CombatEncounter), mover, "moving", ()))
            self.assertIs(next(waiters), first)
            eligible[id(second)] = False
            self.assertEqual(list(waiters), [])
