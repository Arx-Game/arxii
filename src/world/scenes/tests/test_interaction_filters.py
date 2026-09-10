from django.test import TestCase

from world.scenes.constants import InteractionMode
from world.scenes.factories import InteractionFactory, PersonaFactory, PlaceFactory, SceneFactory
from world.scenes.interaction_filters import InteractionFilter
from world.scenes.models import Interaction


class InteractionFilterKindTests(TestCase):
    def test_kind_room_matches_scene_interactions(self) -> None:
        scene = SceneFactory()
        InteractionFactory(scene=scene, place=None, mode=InteractionMode.POSE)
        InteractionFactory(scene=None, place=PlaceFactory(), mode=InteractionMode.POSE)
        qs = InteractionFilter({"kind": "room"}, queryset=Interaction.objects.all()).qs
        self.assertTrue(all(row.scene_id == scene.pk for row in qs))
        self.assertTrue(qs.exists())

    def test_kind_place_matches_place_interactions(self) -> None:
        place = PlaceFactory()
        InteractionFactory(place=place, mode=InteractionMode.POSE)
        InteractionFactory(place=None, scene=SceneFactory(), mode=InteractionMode.POSE)
        qs = InteractionFilter({"kind": "place"}, queryset=Interaction.objects.all()).qs
        self.assertTrue(all(row.place_id == place.pk for row in qs))
        self.assertTrue(qs.exists())

    def test_kind_whisper_matches_whisper_mode(self) -> None:
        InteractionFactory(mode=InteractionMode.WHISPER, place=None, scene=None)
        InteractionFactory(mode=InteractionMode.POSE, place=None, scene=SceneFactory())
        qs = InteractionFilter({"kind": "whisper"}, queryset=Interaction.objects.all()).qs
        self.assertTrue(all(row.mode == InteractionMode.WHISPER for row in qs))
        self.assertTrue(qs.exists())

    def test_kind_unrecognized_value_returns_unfiltered_queryset(self) -> None:
        InteractionFactory(mode=InteractionMode.POSE, place=None, scene=SceneFactory())
        InteractionFactory(place=PlaceFactory())
        qs = InteractionFilter({"kind": "not-a-real-kind"}, queryset=Interaction.objects.all()).qs
        self.assertEqual(qs.count(), Interaction.objects.count())


class InteractionFilterParticipantTests(TestCase):
    def test_participant_matches_writer(self) -> None:
        persona = PersonaFactory()
        interaction = InteractionFactory(persona=persona)
        InteractionFactory()
        qs = InteractionFilter({"participant": persona.pk}, queryset=Interaction.objects.all()).qs
        self.assertEqual(set(qs.values_list("pk", flat=True)), {interaction.pk})

    def test_participant_matches_receiver(self) -> None:
        from world.scenes.place_models import InteractionReceiver

        receiver_persona = PersonaFactory()
        interaction = InteractionFactory()
        InteractionReceiver.objects.create(
            interaction=interaction,
            timestamp=interaction.timestamp,
            persona=receiver_persona,
        )
        InteractionFactory()
        filter_data = {"participant": receiver_persona.pk}
        qs = InteractionFilter(filter_data, queryset=Interaction.objects.all()).qs
        self.assertEqual(set(qs.values_list("pk", flat=True)), {interaction.pk})

    def test_participant_no_match_returns_empty(self) -> None:
        InteractionFactory()
        qs = InteractionFilter({"participant": 999999999}, queryset=Interaction.objects.all()).qs
        self.assertFalse(qs.exists())
