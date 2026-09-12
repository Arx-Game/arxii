"""The room-heard predicate is shared by read visibility and attention counting."""

from django.test import TestCase

from world.scenes.constants import InteractionMode, InteractionVisibility
from world.scenes.factories import InteractionFactory, PersonaFactory, SceneFactory
from world.scenes.managers import room_heard_q
from world.scenes.models import Interaction
from world.scenes.place_models import InteractionReceiver


class RoomHeardPredicateTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.speaker = PersonaFactory()
        cls.listener = PersonaFactory()
        cls.public_pose = InteractionFactory(
            scene=cls.scene,
            persona=cls.speaker,
            visibility=InteractionVisibility.DEFAULT,
        )
        cls.whisper = InteractionFactory(
            scene=cls.scene,
            persona=cls.speaker,
            mode=InteractionMode.WHISPER,
            visibility=InteractionVisibility.DEFAULT,
        )
        InteractionReceiver.objects.create(
            interaction=cls.whisper,
            timestamp=cls.whisper.timestamp,
            persona=cls.listener,
        )
        cls.private_pose = InteractionFactory(
            scene=cls.scene,
            persona=cls.speaker,
            visibility=InteractionVisibility.VERY_PRIVATE,
        )

    def test_public_pose_is_room_heard(self) -> None:
        matched = set(Interaction.objects.filter(room_heard_q()).values_list("id", flat=True))
        self.assertIn(self.public_pose.id, matched)

    def test_whisper_is_not_room_heard(self) -> None:
        matched = set(Interaction.objects.filter(room_heard_q()).values_list("id", flat=True))
        self.assertNotIn(self.whisper.id, matched)

    def test_private_pose_is_not_room_heard(self) -> None:
        matched = set(Interaction.objects.filter(room_heard_q()).values_list("id", flat=True))
        self.assertNotIn(self.private_pose.id, matched)

    def test_each_call_returns_an_independent_q(self) -> None:
        self.assertIsNot(room_heard_q(), room_heard_q())
