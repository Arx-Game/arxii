"""Tests for SceneDetailSerializer.declared_risk (#3433).

Player-visible risk tier for the scene-header badge. Precedence:
scene.running_beat.risk (#3425) -> the active combat encounter's
story_beat.risk -> the scene's PENDING DecisiveCheckMarker's beat risk ->
None. risk == NONE also renders nothing.

Built in setUp rather than setUpTestData: CombatEncounterFactory creates an
Evennia ObjectDB room, and ObjectDB instances are not deepcopyable (see
test_scene_positions_serializer.py's docstring for the same reason).
"""

from __future__ import annotations

from django.test import TestCase

from world.combat.factories import CombatEncounterFactory
from world.scenes.constants import DecisiveCheckMarkerStatus
from world.scenes.factories import SceneFactory
from world.scenes.models import DecisiveCheckMarker
from world.scenes.serializers import SceneDetailSerializer
from world.societies.constants import RenownRisk
from world.stories.factories import BeatFactory


class SceneDeclaredRiskTests(TestCase):
    """SceneDetailSerializer.declared_risk follows the #3433 precedence chain."""

    def setUp(self) -> None:
        self.scene = SceneFactory(running_beat=None)

    def test_running_beat_risk_wins(self) -> None:
        """A running_beat's risk takes precedence over everything else."""
        beat = BeatFactory(risk=RenownRisk.EXTREME)
        self.scene.running_beat = beat
        self.scene.save(update_fields=["running_beat"])

        data = SceneDetailSerializer(self.scene).data

        self.assertEqual(data["declared_risk"], RenownRisk.EXTREME)

    def test_falls_back_to_active_encounter_story_beat(self) -> None:
        """No running_beat: the active encounter's story_beat.risk is used."""
        beat = BeatFactory(risk=RenownRisk.HIGH)
        CombatEncounterFactory(scene=self.scene, story_beat=beat)

        data = SceneDetailSerializer(self.scene).data

        self.assertEqual(data["declared_risk"], RenownRisk.HIGH)

    def test_completed_encounter_is_not_consulted(self) -> None:
        """A completed encounter's story_beat is not the 'active' one."""
        from django.utils import timezone

        beat = BeatFactory(risk=RenownRisk.HIGH)
        CombatEncounterFactory(
            scene=self.scene,
            story_beat=beat,
            completed_at=timezone.now(),
        )

        data = SceneDetailSerializer(self.scene).data

        self.assertIsNone(data["declared_risk"])

    def test_falls_back_to_pending_decisive_marker(self) -> None:
        """No running_beat or active encounter: the PENDING marker's beat.risk is used."""
        beat = BeatFactory(risk=RenownRisk.LOW)
        DecisiveCheckMarker.objects.create(
            scene=self.scene,
            beat=beat,
            status=DecisiveCheckMarkerStatus.PENDING,
        )

        data = SceneDetailSerializer(self.scene).data

        self.assertEqual(data["declared_risk"], RenownRisk.LOW)

    def test_resolved_marker_is_not_consulted(self) -> None:
        """A RESOLVED (non-PENDING) marker is not the scene's live declared risk."""
        beat = BeatFactory(risk=RenownRisk.LOW)
        DecisiveCheckMarker.objects.create(
            scene=self.scene,
            beat=beat,
            status=DecisiveCheckMarkerStatus.RESOLVED,
        )

        data = SceneDetailSerializer(self.scene).data

        self.assertIsNone(data["declared_risk"])

    def test_no_source_renders_no_badge(self) -> None:
        """No running_beat, no active encounter, no PENDING marker -> None."""
        data = SceneDetailSerializer(self.scene).data

        self.assertIsNone(data["declared_risk"])

    def test_risk_none_renders_no_badge(self) -> None:
        """RenownRisk.NONE is undeclared risk, not 'safe' -- renders nothing."""
        beat = BeatFactory(risk=RenownRisk.NONE)
        self.scene.running_beat = beat
        self.scene.save(update_fields=["running_beat"])

        data = SceneDetailSerializer(self.scene).data

        self.assertIsNone(data["declared_risk"])

    def test_declared_risk_carries_no_beat_identity(self) -> None:
        """The player-visible field is the tier string only -- no beat id/name/internals.

        (The leak-table row: beat internals stay on the separately GM/staff-gated
        running_beat field, which itself never rides an unauthenticated payload.)
        """
        beat = BeatFactory(risk=RenownRisk.EXTREME)
        self.scene.running_beat = beat
        self.scene.save(update_fields=["running_beat"])

        data = SceneDetailSerializer(self.scene).data

        self.assertEqual(data["declared_risk"], RenownRisk.EXTREME)
        self.assertIsInstance(data["declared_risk"], str)
        # No request in context -> viewer_can_gm is False -> running_beat (the
        # GM-gated id+risk slice) is absent from this player-shaped payload too.
        self.assertIsNone(data["running_beat"])
