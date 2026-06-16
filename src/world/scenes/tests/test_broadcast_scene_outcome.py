"""Unit/integration tests for broadcast_scene_outcome and render_challenge_outcome_narration."""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase, TestCase

from world.scenes.constants import InteractionMode, RoundStatus, SceneRoundStartReason
from world.scenes.factories import SceneRoundFactory
from world.scenes.interaction_services import (
    broadcast_scene_outcome,
    render_challenge_outcome_narration,
)
from world.scenes.models import Interaction


class RenderChallengeOutcomeNarrationTests(SimpleTestCase):
    def test_success_format(self):
        text = render_challenge_outcome_narration(
            actor_label="Kira",
            challenge_name="Scale the Wall",
            approach_name="Athletics",
            outcome_label="Decisive Success",
            success_level=2,
        )
        assert text == "Kira attempts Scale the Wall (Athletics) and succeeds (Decisive Success)."

    def test_failure_format(self):
        text = render_challenge_outcome_narration(
            actor_label="Kira",
            challenge_name="Scale the Wall",
            approach_name="Athletics",
            outcome_label="Failure",
            success_level=-1,
        )
        assert text == "Kira attempts Scale the Wall (Athletics) and fails (Failure)."

    def test_zero_success_level_reads_as_failure(self):
        text = render_challenge_outcome_narration(
            actor_label="Kira",
            challenge_name="Climb",
            approach_name="Strength",
            outcome_label="Marginal Failure",
            success_level=0,
        )
        assert "fails" in text

    def test_deterministic(self):
        kwargs = {
            "actor_label": "Kira",
            "challenge_name": "Scale the Wall",
            "approach_name": "Athletics",
            "outcome_label": "Marginal Success",
            "success_level": 1,
        }
        assert render_challenge_outcome_narration(**kwargs) == render_challenge_outcome_narration(
            **kwargs
        )


class BroadcastSceneOutcomeTests(TestCase):
    def setUp(self):
        from evennia_extensions.factories import ObjectDBFactory

        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.rnd = SceneRoundFactory(
            room=self.room,
            status=RoundStatus.DECLARING,
            start_reason=SceneRoundStartReason.OPT_IN,
        )

    def test_creates_outcome_interaction(self):
        broadcast_scene_outcome(scene_round=self.rnd, narration="Kira succeeds.")
        assert Interaction.objects.filter(mode=InteractionMode.OUTCOME).count() == 1

    def test_interaction_content_matches_narration(self):
        narration = "Kira attempts Scale the Wall (Athletics) and succeeds (Decisive Success)."
        broadcast_scene_outcome(scene_round=self.rnd, narration=narration)
        interaction = Interaction.objects.get(mode=InteractionMode.OUTCOME)
        assert interaction.content == narration

    def test_empty_narration_returns_none_and_creates_no_interaction(self):
        result = broadcast_scene_outcome(scene_round=self.rnd, narration="")
        assert result is None
        assert Interaction.objects.filter(mode=InteractionMode.OUTCOME).count() == 0

    def test_broadcasts_to_room(self):
        with mock.patch(
            "world.scenes.interaction_services._broadcast_to_location"
        ) as mock_broadcast:
            broadcast_scene_outcome(scene_round=self.rnd, narration="Kira succeeds.")
        mock_broadcast.assert_called_once()
        room_arg = mock_broadcast.call_args[0][0]
        assert room_arg == self.rnd.room

    def test_interaction_mode_is_outcome(self):
        result = broadcast_scene_outcome(scene_round=self.rnd, narration="Kira succeeds.")
        assert result is not None
        assert result.mode == InteractionMode.OUTCOME
