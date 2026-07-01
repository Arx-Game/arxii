"""Tests for BattleRoundContext and the resolver integration."""

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from actions.round_context import get_active_round_context
from world.battles.constants import BattleActionKind
from world.battles.factories import BattleParticipantFactory, BattleRoundFactory
from world.battles.models import BattleActionDeclaration
from world.battles.services import begin_battle_round
from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory
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


class BattleRoundContextRecordDeclarationTests(TestCase):
    def setUp(self) -> None:
        self.participant = BattleParticipantFactory()
        self.technique = TechniqueFactory(action_template=ActionTemplateFactory())
        CharacterTechniqueFactory(
            character=self.participant.character_sheet, technique=self.technique
        )
        begin_battle_round(battle=self.participant.battle)

    def test_record_declaration_writes_technique(self) -> None:
        from world.battles.round_context import BattleRoundContext

        ctx = BattleRoundContext(self.participant)
        ctx.record_declaration(
            self.participant.character_sheet,
            None,
            {
                "action_kind": BattleActionKind.STRIKE,
                "technique": self.technique,
            },
        )
        declaration = BattleActionDeclaration.objects.get(participant=self.participant)
        self.assertEqual(declaration.technique, self.technique)
