from django.test import TestCase

from world.scenes.constants import InteractionMode
from world.scenes.factories import (
    InteractionFactory,
    InteractionReceiverFactory,
    PersonaFactory,
    PlaceFactory,
    SceneFactory,
)
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

    def test_kind_whisper_matches_whisper_mode_with_receivers(self) -> None:
        whisper = InteractionFactory(mode=InteractionMode.WHISPER, place=None, scene=None)
        InteractionReceiverFactory(interaction=whisper)
        InteractionFactory(mode=InteractionMode.POSE, place=None, scene=SceneFactory())
        qs = InteractionFilter({"kind": "whisper"}, queryset=Interaction.objects.all()).qs
        self.assertEqual(set(qs.values_list("pk", flat=True)), {whisper.pk})

    def test_kind_whisper_mode_with_no_receivers_falls_through_to_room(self) -> None:
        """Mirrors `_conversation()`'s precedence: whisper only classifies with receivers."""
        whisper = InteractionFactory(mode=InteractionMode.WHISPER, place=None, scene=None)
        all_interactions = Interaction.objects.all()
        whisper_result = InteractionFilter({"kind": "whisper"}, queryset=all_interactions).qs
        self.assertNotIn(whisper.pk, whisper_result.values_list("pk", flat=True))
        room_result = InteractionFilter({"kind": "room"}, queryset=all_interactions).qs
        self.assertIn(whisper.pk, room_result.values_list("pk", flat=True))

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
        receiver_persona = PersonaFactory()
        interaction = InteractionFactory()
        InteractionReceiverFactory(interaction=interaction, persona=receiver_persona)
        InteractionFactory()
        filter_data = {"participant": receiver_persona.pk}
        qs = InteractionFilter(filter_data, queryset=Interaction.objects.all()).qs
        self.assertEqual(set(qs.values_list("pk", flat=True)), {interaction.pk})

    def test_participant_no_match_returns_empty(self) -> None:
        InteractionFactory()
        qs = InteractionFilter({"participant": 999999999}, queryset=Interaction.objects.all()).qs
        self.assertFalse(qs.exists())
