"""Tests for BattleRoundContext and the resolver integration."""

from django.test import TestCase

from actions.round_context import get_active_round_context
from world.battles.factories import BattleParticipantFactory, BattleRoundFactory
from world.scenes.constants import RoundStatus


class BattleRoundContextTests(TestCase):
    def setUp(self) -> None:
        self.participant = BattleParticipantFactory()
        self.round = BattleRoundFactory(
            battle=self.participant.battle,
            status=RoundStatus.DECLARING,
            round_number=1,
        )

    def test_resolver_finds_active_battle(self) -> None:
        ctx = get_active_round_context(self.participant.character_sheet)
        self.assertIsNotNone(ctx)
        self.assertTrue(ctx.is_declaration_open)
        self.assertEqual(ctx.round_id, (self.participant.battle.pk, 1))
