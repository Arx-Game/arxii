"""A changed pose is announced to its audience as an ids-only frame (#4508).

Endorsing, retracting, reacting and tagging used to reach only the actor's own page.
``notify_interaction_changed`` tells everyone who can see the pose, on commit, and each
page refetches it through the per-viewer REST retrieve.
"""

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.exceptions import EndorsementValidationError
from world.magic.factories import DramaticMomentTypeFactory, SceneEntryEndorsementFactory
from world.magic.services.gain import (
    account_for_sheet,
    create_dramatic_moment_tag,
    create_pose_endorsement,
    create_scene_entry_endorsement,
    retract_pose_endorsement,
)
from world.scenes.constants import InteractionMode, PoseKind, ReactionWindowKind
from world.scenes.factories import (
    InteractionFactory,
    InteractionReceiverFactory,
    PlaceFactory,
    SceneParticipationFactory,
)
from world.scenes.reaction_services import open_reaction_window, react_to_window
from world.scenes.reaction_toggle_services import toggle_interaction_reaction
from world.scenes.tests.test_push_feed_fields import (
    PushScene,
    register_binary_entrance_kind,
    sheet_with_tenure,
)

SEND = "world.scenes.interaction_services._send_changed_frame"


class InteractionChangedTests(PushScene):
    """``PushScene`` seats the author in a room; a bystander shares it."""

    def setUp(self):
        super().setUp()
        self.bystander = CharacterFactory(db_key="Bystander")
        self.bystander.location = self.room
        self.interaction.mode = InteractionMode.POSE
        self.interaction.pose_kind = PoseKind.STANDARD
        self.interaction.save()

    def _endorse(self):
        endorser = sheet_with_tenure()
        SceneParticipationFactory(scene=self.scene, account=account_for_sheet(endorser))
        return endorser, create_pose_endorsement(endorser, self.interaction, self.resonance)

    def _announced(self, send) -> list:
        assert send.call_count == 1
        return list(send.call_args.args[0])

    def test_endorsing_a_pose_announces_it_to_the_room(self):
        with patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            self._endorse()
        audience = self._announced(send)
        assert self.bystander in audience
        assert self.author.character in audience

    def test_retracting_an_endorsement_announces_it(self):
        with self.captureOnCommitCallbacks(execute=True):
            _, endorsement = self._endorse()
        with patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            retract_pose_endorsement(endorsement)
        assert self.bystander in self._announced(send)

    def test_entry_endorsement_announces_the_entrance_pose(self):
        self.interaction.pose_kind = PoseKind.ENTRY
        self.interaction.save()
        endorser = sheet_with_tenure()
        SceneParticipationFactory(scene=self.scene, account=account_for_sheet(endorser))
        with patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            create_scene_entry_endorsement(endorser, self.author, self.scene, self.resonance)
        assert send.call_args.args[1]["interaction_id"] == self.interaction.pk
        assert self.bystander in self._announced(send)

    def test_tagging_a_pose_announces_it(self):
        with patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            create_dramatic_moment_tag(
                character_sheet=self.author,
                moment_type=DramaticMomentTypeFactory(resonance=self.resonance),
                tagged_by=AccountFactory(),
                scene=self.scene,
                interaction=self.interaction,
            )
        assert self.bystander in self._announced(send)

    def test_toggling_a_reaction_announces_it(self):
        with patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            toggle_interaction_reaction(
                interaction=self.interaction, account=AccountFactory(), emoji="x"
            )
        assert self.bystander in self._announced(send)

    def test_window_reaction_announces_it(self):
        reactor = sheet_with_tenure()
        SceneParticipationFactory(scene=self.scene, account=account_for_sheet(reactor))
        register_binary_entrance_kind(self)
        with self.captureOnCommitCallbacks(execute=True):
            window = open_reaction_window(
                interaction=self.interaction, kind=ReactionWindowKind.ENTRANCE
            )
        with patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            try:
                react_to_window(
                    window=window, reactor_persona=reactor.primary_persona, choice="acclaim"
                )
            except ValidationError:
                self.fail("the reaction should have been accepted")
        assert self.bystander in self._announced(send)

    def test_whisper_change_reaches_only_writer_and_receivers(self):
        receiver = sheet_with_tenure()
        receiver.character.location = self.room
        self.interaction.mode = InteractionMode.WHISPER
        self.interaction.save()
        InteractionReceiverFactory(interaction=self.interaction, persona=receiver.primary_persona)
        with patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            toggle_interaction_reaction(
                interaction=self.interaction, account=AccountFactory(), emoji="x"
            )
        audience = self._announced(send)
        assert self.bystander not in audience
        assert self.author.character in audience
        assert receiver.character in audience

    def test_place_scoped_change_reaches_only_writer_and_receivers(self):
        receiver = sheet_with_tenure()
        receiver.character.location = self.room
        self.interaction.place = PlaceFactory()
        self.interaction.save()
        InteractionReceiverFactory(interaction=self.interaction, persona=receiver.primary_persona)
        with patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            toggle_interaction_reaction(
                interaction=self.interaction, account=AccountFactory(), emoji="x"
            )
        audience = self._announced(send)
        assert self.bystander not in audience
        assert {self.author.character, receiver.character} <= set(audience)

    def test_unplaced_writer_falls_back_to_the_scenes_room(self):
        self.author.character.location = None
        self.scene.room = self.room
        with patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            toggle_interaction_reaction(
                interaction=self.interaction, account=AccountFactory(), emoji="x"
            )
        assert self.bystander in self._announced(send)

    def test_no_location_at_all_sends_nothing(self):
        self.author.character.location = None
        with patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            toggle_interaction_reaction(
                interaction=self.interaction, account=AccountFactory(), emoji="x"
            )
        send.assert_not_called()

    def test_every_entrance_pose_of_the_endorsee_is_announced(self):
        self.interaction.pose_kind = PoseKind.ENTRY
        self.interaction.save()
        second = InteractionFactory(
            persona=self.author.primary_persona, pose_kind=PoseKind.ENTRY, scene=self.scene
        )
        endorser = sheet_with_tenure()
        SceneParticipationFactory(scene=self.scene, account=account_for_sheet(endorser))
        with patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            create_scene_entry_endorsement(endorser, self.author, self.scene, self.resonance)
        announced = {call.args[1]["interaction_id"] for call in send.call_args_list}
        assert announced == {self.interaction.pk, second.pk}

    def test_the_real_msg_call_carries_the_ids_only_frame(self):
        with (
            patch.object(self.bystander, "msg") as bystander_msg,
            patch.object(self.author.character, "msg") as author_msg,
            self.captureOnCommitCallbacks(execute=True),
        ):
            toggle_interaction_reaction(
                interaction=self.interaction, account=AccountFactory(), emoji="x"
            )
        expected = {
            "interaction_changed": (
                (),
                {"interaction_id": self.interaction.pk, "scene_id": self.scene.pk},
            )
        }
        bystander_msg.assert_called_once_with(**expected)
        author_msg.assert_called_once_with(**expected)

    def test_failed_endorsement_announces_nothing(self):
        with patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(EndorsementValidationError):
                create_pose_endorsement(self.author, self.interaction, self.resonance)
        send.assert_not_called()

    def test_frame_carries_ids_only(self):
        with patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            self._endorse()
        frame = send.call_args.args[1]
        assert set(frame) == {"interaction_id", "scene_id"}
        assert frame == {"interaction_id": self.interaction.pk, "scene_id": self.scene.pk}

    def test_a_rolled_back_write_announces_nothing(self):
        with patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    self._endorse()
                    raise RuntimeError
            except RuntimeError:
                pass
        send.assert_not_called()


class RetrieveWithoutSceneParamTests(PushScene):
    def test_retrieve_without_scene_param_fills_entry_endorsers(self):
        endorser = CharacterSheetFactory()
        SceneEntryEndorsementFactory(
            endorser_sheet=endorser,
            endorsee_sheet=self.author,
            scene=self.scene,
            resonance=self.resonance,
        )
        viewer = sheet_with_tenure()
        client = APIClient()
        client.force_authenticate(user=account_for_sheet(viewer))
        response = client.get(f"/api/interactions/{self.interaction.pk}/")
        assert response.status_code == 200, response.content
        assert [e["persona_id"] for e in response.data["entry_endorsers"]] == [
            endorser.primary_persona.pk
        ]
