"""Tests for progression-reward actions (ClaimKudos, CastVote, RemoveVote)."""

from django.test import TestCase

from actions.definitions.progression_rewards import (
    CastVoteAction,
    ClaimKudosAction,
    RemoveVoteAction,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.progression.constants import VoteTargetType
from world.progression.factories import KudosClaimCategoryFactory, KudosPointsDataFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import InteractionFactory, PersonaFactory


def _actor_with_account():
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(roster_entry=entry)
    return sheet.character, tenure.player_data.account


class ClaimKudosActionTests(TestCase):
    def test_claim_success_returns_success_result(self) -> None:
        actor, account = _actor_with_account()
        KudosPointsDataFactory(account=account, total_earned=100, total_claimed=0)
        category = KudosClaimCategoryFactory(kudos_cost=10, reward_amount=1, is_active=True)
        result = ClaimKudosAction().run(
            actor=actor,
            claim_category_id=category.pk,
            amount=50,
        )
        self.assertTrue(result.success)

    def test_insufficient_kudos_returns_failure(self) -> None:
        actor, account = _actor_with_account()
        KudosPointsDataFactory(account=account, total_earned=5, total_claimed=0)
        category = KudosClaimCategoryFactory(kudos_cost=10, reward_amount=1, is_active=True)
        result = ClaimKudosAction().run(
            actor=actor,
            claim_category_id=category.pk,
            amount=50,
        )
        self.assertFalse(result.success)

    def test_no_account_returns_failure(self) -> None:
        sheet = CharacterSheetFactory()  # no roster tenure → no account
        result = ClaimKudosAction().run(
            actor=sheet.character,
            claim_category_id=1,
            amount=10,
        )
        self.assertFalse(result.success)


class VoteActionTests(TestCase):
    def test_cast_then_remove(self) -> None:
        voter, _ = _actor_with_account()
        author_persona = PersonaFactory()
        a_entry = RosterEntryFactory(character_sheet=author_persona.character_sheet)
        RosterTenureFactory(roster_entry=a_entry)
        interaction = InteractionFactory(persona=author_persona)

        cast = CastVoteAction().run(
            actor=voter,
            target_type=VoteTargetType.INTERACTION,
            target_id=interaction.pk,
        )
        self.assertTrue(cast.success)
        removed = RemoveVoteAction().run(
            actor=voter,
            target_type=VoteTargetType.INTERACTION,
            target_id=interaction.pk,
        )
        self.assertTrue(removed.success)

    def test_self_vote_returns_failure(self) -> None:
        voter, _account = _actor_with_account()
        # author == voter → ProgressionError.SELF_VOTE
        persona = PersonaFactory(character_sheet=voter.sheet_data)
        interaction = InteractionFactory(persona=persona)
        result = CastVoteAction().run(
            actor=voter,
            target_type=VoteTargetType.INTERACTION,
            target_id=interaction.pk,
        )
        self.assertFalse(result.success)
