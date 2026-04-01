"""Tests for scene completion rewards (vote budget bonuses)."""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.events.constants import EventStatus
from world.events.factories import EventFactory
from world.progression.models import WeeklyVoteBudget
from world.progression.services.scene_rewards import on_scene_finished
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.models import Scene


def _fresh_budget(account: AccountDB) -> WeeklyVoteBudget:
    """Flush cache and return a fresh budget from the DB."""
    WeeklyVoteBudget.flush_instance_cache()
    return WeeklyVoteBudget.objects.get(account=account)


class OnSceneFinishedTest(TestCase):
    """Test on_scene_finished awards vote bonuses to participants."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account1 = AccountDB.objects.create(
            username="scene_reward_1",
            email="sr1@test.com",
        )
        cls.account2 = AccountDB.objects.create(
            username="scene_reward_2",
            email="sr2@test.com",
        )

    def setUp(self) -> None:
        WeeklyVoteBudget.flush_instance_cache()

    def test_increments_vote_budget_for_all_participants(self) -> None:
        """Each participant gets +1 scene bonus vote."""
        scene = SceneFactory()
        SceneParticipationFactory(scene=scene, account=self.account1)
        SceneParticipationFactory(scene=scene, account=self.account2)

        on_scene_finished(scene)

        budget1 = _fresh_budget(self.account1)
        budget2 = _fresh_budget(self.account2)
        assert budget1.scene_bonus_votes == 1
        assert budget2.scene_bonus_votes == 1

    def test_creates_budget_if_none_exists(self) -> None:
        """Budget is auto-created for participants without one."""
        scene = SceneFactory()
        SceneParticipationFactory(scene=scene, account=self.account1)

        assert not WeeklyVoteBudget.objects.filter(account=self.account1).exists()

        on_scene_finished(scene)

        budget = _fresh_budget(self.account1)
        assert budget.scene_bonus_votes == 1

    def test_handles_scene_with_no_participants(self) -> None:
        """No error when a scene has zero participants."""
        scene = SceneFactory()
        on_scene_finished(scene)
        # No exception raised, no budgets created
        assert WeeklyVoteBudget.objects.count() == 0


class EventCompletionTriggersSceneRewardsTest(TestCase):
    """Test that completing an event triggers scene rewards."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountDB.objects.create(
            username="event_reward",
            email="er@test.com",
        )

    def setUp(self) -> None:
        WeeklyVoteBudget.flush_instance_cache()
        Scene.flush_instance_cache()

    def test_complete_event_triggers_scene_rewards(self) -> None:
        """Completing an active event awards scene bonuses to participants."""
        from world.events.services import complete_event, start_event

        event = EventFactory(status=EventStatus.SCHEDULED)

        # Start the event (creates a scene)
        event = start_event(event)
        scene = Scene.objects.get(event=event)

        # Add a participant to the scene
        SceneParticipationFactory(scene=scene, account=self.account)

        # Complete the event (finishes the scene and triggers rewards)
        complete_event(event)

        budget = _fresh_budget(self.account)
        assert budget.scene_bonus_votes == 1
