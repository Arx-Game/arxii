"""
Tests for get_author_account_for_target service function.
"""

from django.test import TestCase

from world.progression.constants import VoteTargetType
from world.progression.services.voting import get_author_account_for_target
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import InteractionFactory, PersonaFactory


class GetAuthorAccountTests(TestCase):
    def test_interaction_author_resolves_to_account(self) -> None:
        persona = PersonaFactory()
        entry = RosterEntryFactory(character_sheet=persona.character_sheet)
        tenure = RosterTenureFactory(roster_entry=entry)
        interaction = InteractionFactory(persona=persona)
        result = get_author_account_for_target(VoteTargetType.INTERACTION, interaction.pk)
        self.assertEqual(result, tenure.player_data.account)

    def test_unknown_target_type_returns_none(self) -> None:
        self.assertIsNone(get_author_account_for_target("nonsense", 1))
