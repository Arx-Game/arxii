"""Tests for the reply parent (#3787): anchoring a thread, and serving it to the reader."""

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
from world.scenes.models import InteractionThread
from world.scenes.thread_services import ReplyTarget


class ReplyParentEdgeTest(TestCase):
    """A reply's thread is anchored on the row it answered, and nests when that row is one.

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

    def _reply_to(self, target, content="He goes down on one knee."):
        with patch(
            "world.scenes.interaction_services._get_account_for_persona",
            return_value=self.account.pk,
        ):
            return create_interaction(
                persona=self.persona,
                content=content,
                mode=InteractionMode.POSE,
                scene=self.scene,
                reply_to=ReplyTarget(interaction_id=target.pk, timestamp=target.timestamp),
            )

    def _thread_of(self, reply) -> InteractionThread:
        return InteractionThread.objects.get(pk=reply.thread_id)

    def test_replying_anchors_the_thread_at_the_target(self):
        target = InteractionFactory(scene=self.scene, mode=InteractionMode.POSE)
        reply = self._reply_to(target)
        thread = self._thread_of(reply)
        self.assertEqual(thread.anchor_interaction_id, target.pk)
        self.assertEqual(thread.anchor_timestamp, target.timestamp)

    def test_the_answered_row_is_not_moved_into_the_thread(self):
        """The #3787 semantic change, stated as an assertion.

        A thread holds the ANSWERS to one row; the row itself is reachable as the
        anchor. If the target were also made a member, the "which pile am I in"
        reading would creep back and nesting would stop meaning anything.
        """
        target = InteractionFactory(scene=self.scene, mode=InteractionMode.POSE)
        self._reply_to(target)
        target.refresh_from_db()
        self.assertIsNone(target.thread_id)

    def test_replying_to_a_combat_outcome_anchors_the_thread(self):
        """The case #3787 was filed for. OUTCOME rows are Narrator-authored."""
        target = InteractionFactory(scene=self.scene, mode=InteractionMode.OUTCOME)
        reply = self._reply_to(target)
        self.assertEqual(self._thread_of(reply).anchor_interaction_id, target.pk)

    def test_replying_to_a_combat_action_anchors_the_thread(self):
        """ACTION rows take a direct objects.create path, not the full wrapper."""
        target = InteractionFactory(scene=self.scene, mode=InteractionMode.ACTION)
        reply = self._reply_to(target)
        self.assertEqual(self._thread_of(reply).anchor_interaction_id, target.pk)

    def test_two_people_answering_the_same_blow_share_one_thread(self):
        """What the per-reply edge table could not express (#3787 rework).

        A bridge wrote one row per reply, each repeating "answers that blow". The
        anchor carries that fact once, so the second answer JOINS the first's thread
        instead of opening a parallel one.
        """
        target = InteractionFactory(scene=self.scene, mode=InteractionMode.OUTCOME)
        first = self._reply_to(target, content="She swears and drops her guard.")
        second = self._reply_to(target, content="He laughs at the blood.")

        self.assertEqual(first.thread_id, second.thread_id)
        self.assertEqual(
            InteractionThread.objects.filter(anchor_interaction_id=target.pk).count(), 1
        )

    def test_answering_a_reply_nests_a_thread(self):
        """A reply to a reply is a nested thread, the way an old mailing list nests."""
        target = InteractionFactory(scene=self.scene, mode=InteractionMode.OUTCOME)
        reply = self._reply_to(target, content="She swears and drops her guard.")
        nested = self._reply_to(reply, content="He steps into the opening.")

        outer = self._thread_of(reply)
        inner = self._thread_of(nested)

        self.assertNotEqual(inner.pk, outer.pk)
        self.assertEqual(inner.anchor_interaction_id, reply.pk)
        self.assertEqual(inner.parent_id, outer.pk)
        self.assertEqual(inner.root_id, outer.pk)
        self.assertIsNone(outer.parent_id)
        self.assertIsNone(outer.root_id)

    def test_a_third_level_keeps_the_root_at_the_top_of_the_tree(self):
        """``root`` is the top of the tree, not the immediate parent."""
        target = InteractionFactory(scene=self.scene, mode=InteractionMode.OUTCOME)
        reply = self._reply_to(target, content="She swears and drops her guard.")
        nested = self._reply_to(reply, content="He steps into the opening.")
        deeper = self._reply_to(nested, content="She turns the blade aside.")

        outer = self._thread_of(reply)
        inner = self._thread_of(nested)
        deepest = self._thread_of(deeper)

        self.assertEqual(deepest.parent_id, inner.pk)
        self.assertEqual(deepest.root_id, outer.pk)

    def test_answering_the_original_parent_again_joins_the_original_thread(self):
        """Nesting never captures later answers to the row that started it."""
        target = InteractionFactory(scene=self.scene, mode=InteractionMode.OUTCOME)
        reply = self._reply_to(target, content="She swears and drops her guard.")
        nested = self._reply_to(reply, content="He steps into the opening.")
        latecomer = self._reply_to(target, content="The crowd surges back from the rail.")

        self.assertEqual(latecomer.thread_id, reply.thread_id)
        self.assertNotEqual(latecomer.thread_id, nested.thread_id)

    def test_a_reply_always_carries_a_thread_id(self):
        """The invariant ``_reply_parent_payload``'s early return depends on.

        ``assign_interaction_thread`` is the only writer of ``Interaction.thread``, and
        the thread it writes is always anchored. That is what lets the live push skip
        the parent lookup for every row with no ``thread_id`` instead of paying a
        SELECT on every single push. If this ever fails, remove that early return
        before doing anything else - it would be silently dropping parent chips.
        """
        target = InteractionFactory(scene=self.scene, mode=InteractionMode.POSE)
        reply = self._reply_to(target)
        self.assertIsNotNone(reply.thread_id)
        self.assertIsNotNone(self._thread_of(reply).anchor_interaction_id)

    def test_an_unthreaded_pose_has_no_parent(self):
        pose = create_interaction(
            persona=self.persona,
            content="Someone drops a glass.",
            mode=InteractionMode.POSE,
            scene=self.scene,
        )
        self.assertIsNone(pose.thread_id)


class ReplyToSerializationTest(TestCase):
    """``get_reply_to`` is gated on the parent's own visibility, not on the anchor existing."""

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

    def test_the_chip_carries_no_actor_for_a_concealed_outcome(self):
        """A concealed combat outcome must never be named by the chip it anchors.

        The payload is an id and a timestamp and nothing else, so there is no field
        for a persona name, content excerpt or mode to leak through. Asserted on the
        keys rather than on one value: a future addition to this dict is exactly how
        an actor would get named, and this is the test that would fail.
        """
        scene = SceneFactory()
        persona = PersonaFactory()
        author = AccountFactory()
        target = InteractionFactory(
            scene=scene, persona=persona, writer_account=author, mode=InteractionMode.OUTCOME
        )
        reply = self._create_reply(persona=persona, scene=scene, account=author, target=target)

        data = InteractionListSerializer(reply, context={"request": self._request_for(author)}).data
        self.assertEqual(set(data["reply_to"]), {"id", "timestamp"})


class RootThreadIdSerializationTest(TestCase):
    """``root_thread_id`` is the one key every row of a single exchange shares.

    A row's own thread is what it ANSWERS, so a back-and-forth is several nested
    threads by construction and ``thread_id`` alone would split one exchange into a
    card per level in the reader. These pin the grouping key the reader actually
    uses (``ThreadedNarrativeReader``).
    """

    def _request_for(self, account):
        request = APIRequestFactory().get("/")
        request.user = account
        return request

    def _reply(self, *, persona, scene, account, target, content):
        with patch(
            "world.scenes.interaction_services._get_account_for_persona",
            return_value=account.pk,
        ):
            return create_interaction(
                persona=persona,
                content=content,
                mode=InteractionMode.POSE,
                scene=scene,
                reply_to=ReplyTarget(interaction_id=target.pk, timestamp=target.timestamp),
            )

    def setUp(self):
        self.scene = SceneFactory()
        self.persona = PersonaFactory()
        self.author = AccountFactory()
        self.opening = InteractionFactory(
            scene=self.scene,
            persona=self.persona,
            writer_account=self.author,
            mode=InteractionMode.POSE,
        )

    def _serialized(self, interaction):
        return InteractionListSerializer(
            interaction, context={"request": self._request_for(self.author)}
        ).data

    def test_a_pose_that_answers_nothing_has_no_root(self):
        self.assertIsNone(self._serialized(self.opening)["root_thread_id"])

    def test_a_first_level_reply_is_its_own_root(self):
        """Null, matching ``InteractionThread.root``; the reader falls back to thread_id."""
        reply = self._reply(
            persona=self.persona,
            scene=self.scene,
            account=self.author,
            target=self.opening,
            content="She parries.",
        )
        data = self._serialized(reply)
        self.assertIsNone(data["root_thread_id"])
        self.assertEqual(data["thread_id"], str(reply.thread_id))

    def test_a_nested_reply_carries_the_top_of_the_tree(self):
        reply = self._reply(
            persona=self.persona,
            scene=self.scene,
            account=self.author,
            target=self.opening,
            content="She parries.",
        )
        nested = self._reply(
            persona=self.persona,
            scene=self.scene,
            account=self.author,
            target=reply,
            content="He steps into the opening.",
        )
        deeper = self._reply(
            persona=self.persona,
            scene=self.scene,
            account=self.author,
            target=nested,
            content="She turns the blade aside.",
        )

        root_key = str(reply.thread_id)
        self.assertNotEqual(nested.thread_id, reply.thread_id)
        self.assertEqual(self._serialized(nested)["root_thread_id"], root_key)
        self.assertEqual(self._serialized(deeper)["root_thread_id"], root_key)


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

    def test_a_pose_that_answers_nothing_costs_no_parent_lookup(self):
        """The saving the docstring claims, pinned so it cannot silently regress.

        ``thread_id`` is a plain column on the row, so the "answers nothing" branch
        must not touch the database at all. Asserted as an exact count rather than a
        budget: the point is that the lookup is absent, and a budget that happened to
        have a spare slot would not notice one coming back.
        """
        pose = create_interaction(
            persona=self.persona,
            content="Someone drops a glass.",
            mode=InteractionMode.POSE,
            scene=self.scene,
        )
        pose.refresh_from_db()

        with patch("world.scenes.interaction_services._broadcast_to_location"):
            with self.assertNumQueries(0):
                self.assertIsNone(_reply_parent_payload(pose))

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
        """Anchor a thread at *target* directly, bypassing the reply refusal.

        ``assign_interaction_thread`` already refuses most of these venues at write
        time (ADR-0293 decision 1), but the recorded anchor outlives the shape it was
        written against: a room-heard parent can be escalated afterwards with
        ``mark_very_private``. The wire gate has to hold on the shape the parent has
        NOW, so these cases assert it against an anchor that exists.

        Built exactly as the real writer builds it - an anchored thread, with the
        reply pointed at it. ``_reply_parent_payload`` returns early for a row with no
        ``thread_id``, so a reply left unthreaded would make every case below pass for
        the wrong reason, never reaching the shape gate they exist to test.
        """
        reply = create_interaction(
            persona=self.persona,
            content="He goes down on one knee.",
            mode=InteractionMode.POSE,
            scene=self.scene,
        )
        reply.thread = InteractionThread.objects.create(
            anchor_interaction_id=target.pk,
            anchor_timestamp=target.timestamp,
            holder_kind=InteractionThread.HolderKind.SCENE,
            holder_id=self.scene.pk,
            scene_id=self.scene.pk,
        )
        reply.save(update_fields=["thread"])
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
        """The reachable case: the anchor was legitimate; the parent went private after."""
        target = InteractionFactory(scene=self.scene, mode=InteractionMode.OUTCOME)
        reply = self._edge_to(target)
        self.assertIsNotNone(_reply_parent_payload(reply))

        target.visibility = InteractionVisibility.PERCEIVED_ONLY
        target.save(update_fields=["visibility"])

        self.assertIsNone(_reply_parent_payload(reply))

    def test_a_parent_in_another_scene_is_never_put_on_the_wire(self):
        target = InteractionFactory(scene=SceneFactory(), mode=InteractionMode.POSE)

        self.assertIsNone(_reply_parent_payload(self._edge_to(target)))
