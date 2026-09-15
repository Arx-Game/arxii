"""Scene completion side effects: reaction-window settlement only (#3738 removed vote bonuses)."""

from unittest.mock import patch

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.events.constants import EventStatus
from world.events.factories import EventFactory
from world.progression.services.scene_rewards import on_scene_finished
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.models import Scene


class OnSceneFinishedTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountDB.objects.create(username="scene_reward_1", email="sr1@test.com")

    @patch("world.scenes.reaction_services.settle_windows_for_scene")
    def test_settles_the_scenes_reaction_windows(self, settle) -> None:
        scene = SceneFactory()
        SceneParticipationFactory(scene=scene, account=self.account)

        on_scene_finished(scene)

        settle.assert_called_once_with(scene)

    @patch("world.scenes.reaction_services.settle_windows_for_scene")
    def test_a_scene_with_no_participants_still_settles(self, settle) -> None:
        scene = SceneFactory()
        on_scene_finished(scene)
        settle.assert_called_once_with(scene)


class EventCompletionTriggersSceneRewardsTest(TestCase):
    def setUp(self) -> None:
        Scene.flush_instance_cache()

    @patch("world.scenes.reaction_services.settle_windows_for_scene")
    def test_complete_event_settles_its_scene(self, settle) -> None:
        from world.events.services import complete_event, start_event

        event = start_event(EventFactory(status=EventStatus.SCHEDULED))
        scene = Scene.objects.get(event=event)

        complete_event(event)

        settle.assert_called_once()
        assert settle.call_args.args[0].pk == scene.pk
