"""Tests for progression-reward actions."""

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.progression_rewards import (
    CastVoteAction,
    ClaimKudosAction,
    ClaimRandomSceneAction,
    ClearPathIntentAction,
    RemoveVoteAction,
    SetPathIntentAction,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.progression.constants import VoteTargetType
from world.progression.factories import (
    KudosClaimCategoryFactory,
    KudosPointsDataFactory,
    RandomSceneTargetFactory,
)
from world.progression.models.path_intent import PathIntent
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


class RandomSceneActionTests(TestCase):
    @patch("world.progression.services.random_scene.validate_random_scene_claim", return_value=True)
    def test_claim_success(self, mock_validate) -> None:
        claimer, account = _actor_with_account()
        target_persona = PersonaFactory()
        t_entry = RosterEntryFactory(character_sheet=target_persona.character_sheet)
        RosterTenureFactory(roster_entry=t_entry)
        target = RandomSceneTargetFactory(account=account, target_persona=target_persona)
        result = ClaimRandomSceneAction().run(actor=claimer, target_id=target.pk)
        self.assertTrue(result.success)
        target.refresh_from_db()
        self.assertTrue(target.claimed)


class PathIntentActionTests(TestCase):
    def setUp(self) -> None:
        PathIntent.flush_instance_cache()

    def test_set_then_clear(self) -> None:
        actor, _ = _actor_with_account()
        path = PathFactory(name="Champion")
        result = SetPathIntentAction().run(actor=actor, path_id=path.pk)
        self.assertTrue(result.success)
        self.assertTrue(PathIntent.objects.filter(character_sheet=actor.sheet_data).exists())
        cleared = ClearPathIntentAction().run(actor=actor)
        self.assertTrue(cleared.success)
        self.assertFalse(PathIntent.objects.filter(character_sheet=actor.sheet_data).exists())
