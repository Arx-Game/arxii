"""Tests for the reply parent edge (#3787): writing it, and serving it to the reader."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import InteractionMode, InteractionVisibility, ScenePrivacyMode
from world.scenes.factories import (
    InteractionFactory,
    PersonaFactory,
    PlaceFactory,
    SceneFactory,
)
from world.scenes.interaction_serializers import InteractionListSerializer
from world.scenes.interaction_services import (
    _reply_parent_payload,
    create_interaction,
    push_interaction,
)
from world.scenes.models import InteractionReply
from world.scenes.thread_services import ReplyTarget


class ReplyParentEdgeTest(TestCase):
    """A reply records which interaction it answered, and the reader can read it.

    ``PersonaFactory()`` alone has no roster tenure, so ``_get_account_for_persona``
    resolves to ``None`` and ``assign_interaction_thread`` refuses (account_id is
    required). Mocking it to a real account is the established pattern for this
    exact scenario - see ``test_create_interaction_assigns_thread_atomically`` in
    ``test_threading.py``.
    """

    @classmethod
    def setUpTestData(cls):
        cls.scene = SceneFactory()
        cls.persona = PersonaFactory()
        cls.account = AccountFactory()

    def _reply_to(self, target):
        with patch(
            "world.scenes.interaction_services._get_account_for_persona",
            return_value=self.account.pk,
        ):
            return create_interaction(
                persona=self.persona,
                content="He goes down on one knee.",
                mode=InteractionMode.POSE,
                scene=self.scene,
                reply_to=ReplyTarget(interaction_id=target.pk, timestamp=target.timestamp),
            )

    def test_replying_writes_the_parent_edge(self):
        target = InteractionFactory(scene=self.scene, mode=InteractionMode.POSE)
        reply = self._reply_to(target)
        edge = InteractionReply.objects.get(interaction=reply)
        self.assertEqual(edge.parent_id, target.pk)
        self.assertEqual(edge.parent_timestamp, target.timestamp)

    def test_replying_to_a_combat_outcome_writes_the_edge(self):
        """The case #3787 was filed for. OUTCOME rows are Narrator-authored."""
        target = InteractionFactory(scene=self.scene, mode=InteractionMode.OUTCOME)
        reply = self._reply_to(target)
        self.assertTrue(InteractionReply.objects.filter(interaction=reply).exists())

    def test_replying_to_a_combat_action_writes_the_edge(self):
        """ACTION rows take a direct objects.create path, not the full wrapper."""
        target = InteractionFactory(scene=self.scene, mode=InteractionMode.ACTION)
        reply = self._reply_to(target)
        self.assertTrue(InteractionReply.objects.filter(interaction=reply).exists())

    def test_an_unthreaded_pose_has_no_parent(self):
        pose = create_interaction(
            persona=self.persona,
            content="Someone drops a glass.",
            mode=InteractionMode.POSE,
            scene=self.scene,
        )
        self.assertFalse(InteractionReply.objects.filter(interaction=pose).exists())


class ReplyToSerializationTest(TestCase):
    """``get_reply_to`` is gated on the parent's own visibility, not the edge's existence."""

    def _request_for(self, account):
        request = APIRequestFactory().get("/")
        request.user = account
        return request

    def _create_reply(self, *, persona, scene, account, target):
        with patch(
            "world.scenes.interaction_services._get_account_for_persona",
            return_value=account.pk,
        ):
            return create_interaction(
                persona=persona,
                content="He goes down on one knee.",
                mode=InteractionMode.POSE,
                scene=scene,
                reply_to=ReplyTarget(interaction_id=target.pk, timestamp=target.timestamp),
            )

    def test_reply_to_present_when_viewer_can_see_the_parent(self):
        scene = SceneFactory()
        persona = PersonaFactory()
        author = AccountFactory()
        target = InteractionFactory(
            scene=scene, persona=persona, writer_account=author, mode=InteractionMode.POSE
        )
        reply = self._create_reply(persona=persona, scene=scene, account=author, target=target)

        # Public scene, default visibility: even an unrelated authenticated account
        # already reads it, since the parent itself is room-heard-public.
        viewer = AccountFactory()
        data = InteractionListSerializer(reply, context={"request": self._request_for(viewer)}).data
        expected = {"id": str(target.pk), "timestamp": target.timestamp.isoformat()}
        self.assertEqual(data["reply_to"], expected)

    def test_reply_to_is_none_when_viewer_cannot_see_the_parent(self):
        private_scene = SceneFactory(privacy_mode=ScenePrivacyMode.PRIVATE)
        persona = PersonaFactory()
        author = AccountFactory()
        target = InteractionFactory(
            scene=private_scene,
            persona=persona,
            writer_account=author,
            mode=InteractionMode.POSE,
        )
        reply = self._create_reply(
            persona=persona, scene=private_scene, account=author, target=target
        )

        # This account is not the writer/receiver party, never present, never a
        # participant or GM of the private scene - visible_to() excludes it.
        outsider = AccountFactory()
        data = InteractionListSerializer(
            reply, context={"request": self._request_for(outsider)}
        ).data
        self.assertIsNone(data["reply_to"])
        self.assertEqual(data["id"], reply.pk)


class ReplyToWebSocketPayloadTest(TestCase):
    """The live push carries the parent chip too, on the same shape REST returns.

    Without this the chip appeared for the sender only and every other viewer waited
    for a refetch, leaving Screen 2 of the approved design live-incomplete. The WS gate
    is structural rather than per viewer (see ``_reply_parent_payload``): one payload
    goes to the whole room, so it sends the parent only when the parent is room-heard
    in this same scene, and ``None`` for anything narrower.
    """

    @classmethod
    def setUpTestData(cls):
        cls.room = ObjectDBFactory(
            db_key="The Long Gallery", db_typeclass_path="typeclasses.rooms.Room"
        )
        cls.scene = SceneFactory(location=cls.room)
        character = CharacterFactory(location=cls.room)
        sheet = CharacterSheetFactory(character=character)
        cls.persona = PersonaFactory(character_sheet=sheet)
        cls.account = AccountFactory()

    def _reply_to(self, target, **kwargs):
        with patch(
            "world.scenes.interaction_services._get_account_for_persona",
            return_value=self.account.pk,
        ):
            return create_interaction(
                persona=self.persona,
                content="He goes down on one knee.",
                mode=InteractionMode.POSE,
                scene=self.scene,
                reply_to=ReplyTarget(interaction_id=target.pk, timestamp=target.timestamp),
                **kwargs,
            )

    def test_push_payload_carries_the_parent_on_the_rest_shape(self):
        target = InteractionFactory(scene=self.scene, mode=InteractionMode.OUTCOME)
        reply = self._reply_to(target)

        with patch("world.scenes.interaction_services._broadcast_to_location") as broadcast:
            push_interaction(reply)

        payload = broadcast.call_args.args[1]
        self.assertEqual(
            payload["reply_to"],
            {"id": str(target.pk), "timestamp": target.timestamp.isoformat()},
        )

    def test_a_pose_that_answers_nothing_sends_a_null_parent(self):
        pose = create_interaction(
            persona=self.persona,
            content="Someone drops a glass.",
            mode=InteractionMode.POSE,
            scene=self.scene,
        )

        with patch("world.scenes.interaction_services._broadcast_to_location") as broadcast:
            push_interaction(pose)

        self.assertIsNone(broadcast.call_args.args[1]["reply_to"])

    def _edge_to(self, target):
        """Write the parent edge directly, bypassing the reply refusal.

        ``assign_interaction_thread`` already refuses most of these venues at write
        time (ADR-0291 decision 1), but the recorded edge outlives the shape it was
        written against: a room-heard parent can be escalated afterwards with
        ``mark_very_private``. The wire gate has to hold on the shape the parent has
        NOW, so these cases assert it against an edge that exists.
        """
        reply = create_interaction(
            persona=self.persona,
            content="He goes down on one knee.",
            mode=InteractionMode.POSE,
            scene=self.scene,
        )
        InteractionReply.objects.create(
            interaction=reply,
            timestamp=reply.timestamp,
            parent=target,
            parent_timestamp=target.timestamp,
        )
        return reply

    def test_a_whispered_parent_is_never_put_on_the_wire(self):
        """The privacy gate: a directed parent reaches only its party, so it sends None."""
        other = PersonaFactory()
        target = InteractionFactory(scene=self.scene, mode=InteractionMode.WHISPER)
        target.receivers.create(persona=other, timestamp=target.timestamp)

        self.assertIsNone(_reply_parent_payload(self._edge_to(target)))

    def test_a_place_scoped_parent_is_never_put_on_the_wire(self):
        target = InteractionFactory(
            scene=self.scene, mode=InteractionMode.POSE, place=PlaceFactory()
        )

        self.assertIsNone(_reply_parent_payload(self._edge_to(target)))

    def test_a_parent_escalated_after_the_reply_stops_going_on_the_wire(self):
        """The reachable case: the edge was legitimate; the parent went private after."""
        target = InteractionFactory(scene=self.scene, mode=InteractionMode.OUTCOME)
        reply = self._edge_to(target)
        self.assertIsNotNone(_reply_parent_payload(reply))

        target.visibility = InteractionVisibility.PERCEIVED_ONLY
        target.save(update_fields=["visibility"])

        self.assertIsNone(_reply_parent_payload(reply))

    def test_a_parent_in_another_scene_is_never_put_on_the_wire(self):
        target = InteractionFactory(scene=SceneFactory(), mode=InteractionMode.POSE)

        self.assertIsNone(_reply_parent_payload(self._edge_to(target)))
