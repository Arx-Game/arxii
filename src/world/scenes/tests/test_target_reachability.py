"""Tests for #3787 Task 4: reachability applied to tagged interaction targets.

The live defect: ``target_personas`` appeared nowhere in
``InteractionQuerySet.visible_to`` (``world/scenes/managers.py``). Targets resolve
purely by room presence (``resolve_characters_by_name(target_names,
character.location)``), so a pose written at a Place (which auto-populates
``receivers`` from ``PlacePresence``, making the row DIRECTED) could name a
persona sitting at a different table in the same room -- the
``InteractionTargetPersona`` row was written, the request returned success, and
the tagged persona could never read it.

Each "refused" test below BREAKS the invariant first (constructs a genuinely
unreachable target) and asserts both the typed refusal AND that nothing was
written -- a guard is not verified until it has been watched to fail.
"""

from __future__ import annotations

from unittest.mock import patch
import uuid

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from actions.definitions.communication import PoseAction
from actions.types import ActionResult
from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode, InteractionVisibility
from world.scenes.factories import PersonaFactory, PlaceFactory, PlacePresenceFactory
from world.scenes.interaction_services import create_interaction
from world.scenes.models import Interaction, InteractionTargetPersona
from world.scenes.reachability import UnreachableError

_HINT = "Address the room to reach them, or send a whisper. Your draft is kept."


def _persona_at_place(place) -> object:
    """Build a Persona whose character sits at ``place`` (a genuine PlacePresence)."""
    persona = PersonaFactory()
    PlacePresenceFactory(place=place, persona=persona)
    return persona


def _persona_in_room(room) -> object:
    """Build a Persona whose character is physically located in ``room`` (no Place)."""
    character = CharacterFactory(location=room)
    sheet = CharacterSheetFactory(character=character)
    return sheet.primary_persona


class TestCreateInteractionRefusesUnreachableTargets(TestCase):
    """Service-layer proof: ``create_interaction`` is the shared choke point."""

    def _two_places_in_one_room(self):
        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        room_profile = RoomProfileFactory(objectdb=room)
        place_a = PlaceFactory(room=room_profile, name="the bar")
        place_b = PlaceFactory(room=room_profile, name="the hearth")
        return place_a, place_b

    def test_tagging_persona_at_another_place_is_refused(self) -> None:
        """Breaks the invariant: names someone sitting at a DIFFERENT table."""
        place_a, place_b = self._two_places_in_one_room()
        writer = _persona_at_place(place_a)
        target = _persona_at_place(place_b)

        interaction_count = Interaction.objects.count()
        target_row_count = InteractionTargetPersona.objects.count()

        with self.assertRaises(UnreachableError) as error:
            create_interaction(
                persona=writer,
                content="murmurs about the deal.",
                mode=InteractionMode.POSE,
                place=place_a,
                target_personas=[target],
            )

        exc = error.exception
        assert exc.code == "target_unreachable"
        assert exc.personas == [target]
        assert str(exc) == f"{target.name} is across the room and will not see table talk."
        assert exc.venue_hint == _HINT

        # Nothing was written by the refused attempt -- not the Interaction row,
        # not the target row (the draft is preserved by the caller, not us).
        assert Interaction.objects.count() == interaction_count
        assert InteractionTargetPersona.objects.count() == target_row_count

    def test_tagging_two_unreachable_personas_names_both(self) -> None:
        place_a, place_b = self._two_places_in_one_room()
        writer = _persona_at_place(place_a)
        first_target = _persona_at_place(place_b)
        second_target = _persona_at_place(place_b)

        with self.assertRaises(UnreachableError) as error:
            create_interaction(
                persona=writer,
                content="murmurs about the deal.",
                mode=InteractionMode.POSE,
                place=place_a,
                target_personas=[first_target, second_target],
            )

        exc = error.exception
        assert set(exc.personas) == {first_target, second_target}
        assert str(exc) == (
            f"{first_target.name} and {second_target.name} are across the room "
            "and will not see table talk."
        )

    def test_tagging_persona_at_same_place_succeeds(self) -> None:
        """Positive case: the fix does not simply refuse everything."""
        place_a, _place_b = self._two_places_in_one_room()
        writer = _persona_at_place(place_a)
        target = _persona_at_place(place_a)

        interaction = create_interaction(
            persona=writer,
            content="leans in and murmurs.",
            mode=InteractionMode.POSE,
            place=place_a,
            target_personas=[target],
        )

        assert InteractionTargetPersona.objects.filter(
            interaction=interaction, persona=target
        ).exists()

    def test_place_presence_lookup_is_batched_not_per_target(self) -> None:
        """Fix round 1 finding 2: one query for N targets, not N queries.

        Before the fix, ``persona_can_receive``'s place branch issued its own
        ``PlacePresence`` query per call, so validating 3 tagged targets meant 3
        queries. ``create_interaction`` now prefetches the whole set once.
        """
        place_a, _place_b = self._two_places_in_one_room()
        writer = _persona_at_place(place_a)
        targets = [_persona_at_place(place_a) for _ in range(3)]

        with CaptureQueriesContext(connection) as ctx:
            create_interaction(
                persona=writer,
                content="murmurs to the table.",
                mode=InteractionMode.POSE,
                place=place_a,
                target_personas=targets,
            )

        # Distinct from the pre-existing (single, unrelated) auto-populate-receivers
        # query at the top of create_interaction, which ALSO touches PlacePresence
        # (a persona_id = placepresence.persona_id join condition matches too
        # loose a filter) but selects straight off "arxii_persona" -- match
        # narrowly on the validation query's own shape, a bare values_list
        # persona_id SELECT with placepresence itself as the FROM table.
        reachability_queries = [
            q
            for q in ctx.captured_queries
            if 'from "arxii_placepresence" where' in q["sql"].lower()
        ]
        assert len(reachability_queries) == 1, ctx.captured_queries

    def test_tagging_persona_outside_explicit_receivers_is_refused(self) -> None:
        """Directed-without-place shape: explicit receivers narrow the audience too."""
        writer = PersonaFactory()
        receiver = PersonaFactory()
        outsider = PersonaFactory()

        interaction_count = Interaction.objects.count()

        with self.assertRaises(UnreachableError) as error:
            create_interaction(
                persona=writer,
                content="mutters to the group.",
                mode=InteractionMode.POSE,
                receivers=[receiver],
                target_personas=[outsider],
            )

        assert error.exception.personas == [outsider]
        assert Interaction.objects.count() == interaction_count

    def test_tagging_a_receiver_succeeds(self) -> None:
        writer = PersonaFactory()
        receiver = PersonaFactory()

        interaction = create_interaction(
            persona=writer,
            content="mutters to the group.",
            mode=InteractionMode.POSE,
            receivers=[receiver],
            target_personas=[receiver],
        )

        assert InteractionTargetPersona.objects.filter(
            interaction=interaction, persona=receiver
        ).exists()

    def test_tagging_persona_in_open_room_without_scene_still_succeeds(self) -> None:
        """Regression guard: the room-heard shape must not need a Scene.

        Fix round 1 finding 1: this task originally exempted the plain
        room-heard shape (no place, no explicit receivers, not a whisper) from
        the ``persona_can_receive`` check entirely, because that predicate's
        room-heard branch refused outright whenever ``scene`` was None. That
        exemption lived in the shared ``create_interaction`` (~15 callers),
        while the invariant that made it safe (target resolution already
        bound to the writer's own location) belonged to exactly one of them --
        any other caller passing a room-heard shape with escalated visibility
        would have bypassed the guard silently. The real fix is in
        ``persona_can_receive`` itself: it now takes ``location`` as a fallback
        room to test presence against when there is no ``Scene``. This test
        proves the SAME scene-less tagging case still succeeds -- now because
        the predicate answers it correctly, not because the caller skipped
        asking.
        """
        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        writer = _persona_in_room(room)
        target = _persona_in_room(room)

        interaction = create_interaction(
            persona=writer,
            content="waves.",
            mode=InteractionMode.POSE,
            scene=None,
            place=None,
            target_personas=[target],
        )

        assert InteractionTargetPersona.objects.filter(
            interaction=interaction, persona=target
        ).exists()

    def test_tagging_persona_elsewhere_without_scene_is_refused(self) -> None:
        """Breaks the invariant the old exemption could never have caught.

        With no ``Scene`` and a target genuinely NOT in the writer's room, the
        old shape-only exemption skipped the check entirely and this would have
        been (wrongly) accepted. The adapted predicate refuses it correctly.
        """
        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        other_room = ObjectDBFactory(db_key="Cellar", db_typeclass_path="typeclasses.rooms.Room")
        writer = _persona_in_room(room)
        target = _persona_in_room(other_room)

        interaction_count = Interaction.objects.count()

        with self.assertRaises(UnreachableError) as error:
            create_interaction(
                persona=writer,
                content="waves.",
                mode=InteractionMode.POSE,
                scene=None,
                place=None,
                target_personas=[target],
            )

        assert error.exception.personas == [target]
        assert Interaction.objects.count() == interaction_count

    def test_room_heard_target_with_escalated_visibility_is_refused(self) -> None:
        """The exact case fix round 1 finding 1 named: visibility must still gate

        the room-heard branch even with the new no-scene location fallback. If the
        ``visibility != DEFAULT`` check were ever removed or short-circuited by the
        location fallback, this would wrongly succeed -- the target IS standing in
        the room, but a PERCEIVED_ONLY/VERY_PRIVATE room-heard row still isn't
        reachable to anyone (see ``persona_can_receive``'s module docstring).
        """
        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        writer = _persona_in_room(room)
        target = _persona_in_room(room)

        interaction_count = Interaction.objects.count()

        with self.assertRaises(UnreachableError) as error:
            create_interaction(
                persona=writer,
                content="declares to the room.",
                mode=InteractionMode.POSE,
                scene=None,
                place=None,
                target_personas=[target],
                visibility=InteractionVisibility.VERY_PRIVATE,
            )

        assert error.exception.personas == [target]
        assert Interaction.objects.count() == interaction_count


class TestPoseActionRefusesUnreachableTargets(TestCase):
    """Telnet parity (#3787 spec decision 7): the same refusal via ``PoseAction``.

    Telnet reaches ``create_interaction`` through ``record_interaction`` without
    ever passing through the DRF view, so the refusal must be enforced at the
    service layer (this module) and translated by ``Action.run()`` -- the single
    telnet+web chokepoint (``actions/base.py``) -- exactly as it already does for
    ``InteractionThreadError``.
    """

    def setUp(self) -> None:
        patcher = patch("world.scenes.interaction_services.push_interaction")
        self.mock_push = patcher.start()
        self.addCleanup(patcher.stop)

    def test_pose_at_place_targeting_persona_at_another_place_is_refused(self) -> None:
        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        room_profile = RoomProfileFactory(objectdb=room)
        place_a = PlaceFactory(room=room_profile, name="the bar")
        place_b = PlaceFactory(room=room_profile, name="the hearth")

        char_a = CharacterFactory(db_key="Alice", location=room)
        sheet_a = CharacterSheetFactory(character=char_a)
        PlacePresenceFactory(place=place_a, persona=sheet_a.primary_persona)

        char_b = CharacterFactory(db_key="Bob", location=room)
        sheet_b = CharacterSheetFactory(character=char_b)
        PlacePresenceFactory(place=place_b, persona=sheet_b.primary_persona)

        interaction_count = Interaction.objects.count()
        target_row_count = InteractionTargetPersona.objects.count()

        action = PoseAction()
        result = action.run(actor=char_a, text="murmurs to Bob.", targets=[char_b], place=place_a)

        assert isinstance(result, ActionResult)
        assert result.success is False
        # #3787 Task 8: the venue hint is the actionable half of the refusal
        # (spec decision 4) -- Action.run()'s except clause appends it so a
        # telnet player is told where Bob IS reachable, not just that he isn't
        # here.
        assert result.message == ("Bob is across the room and will not see table talk. " + _HINT)
        assert Interaction.objects.count() == interaction_count
        assert InteractionTargetPersona.objects.count() == target_row_count

    def test_pose_command_targeting_unreachable_persona_tells_telnet_the_hint(self) -> None:
        """Genuine telnet-path proof (#3787 Task 8): drives ``CmdPose`` itself,
        not just ``PoseAction.run()`` -- the same seam ``ArxCommand._execute()``
        uses in production, capturing exactly what the player's client receives.
        """
        from commands.evennia_overrides.communication import CmdPose

        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        room_profile = RoomProfileFactory(objectdb=room)
        place_a = PlaceFactory(room=room_profile, name="the bar")
        place_b = PlaceFactory(room=room_profile, name="the hearth")

        char_a = CharacterFactory(db_key="Alice", location=room)
        sheet_a = CharacterSheetFactory(character=char_a)
        PlacePresenceFactory(place=place_a, persona=sheet_a.primary_persona)

        char_b = CharacterFactory(db_key="Bob", location=room)
        sheet_b = CharacterSheetFactory(character=char_b)
        PlacePresenceFactory(place=place_b, persona=sheet_b.primary_persona)

        messages: list[object] = []
        char_a.msg = lambda *args, **kwargs: messages.append((args, kwargs))

        cmd = CmdPose()
        cmd.caller = char_a
        cmd.action = PoseAction()
        # PoseAction's `place` kwarg (the writer's own venue) isn't parsed from
        # telnet text by CmdPose -- it's resolved in `execute()` via
        # `_resolve_pose_place`. Set the caller's PlacePresence-derived venue
        # the way that resolver does, by patching `resolve_action_args` to add
        # it, mirroring `CmdTabletalk` (the actual telnet surface for a
        # Place-scoped pose) without duplicating its whole grammar here.
        cmd.args = " @Bob murmurs across the room."
        cmd.raw_string = "pose @Bob murmurs across the room."
        cmd.cmdset = None
        cmd.cmdset_providers = {}
        cmd.session = None
        cmd.account = None
        cmd.obj = None

        original_resolve = cmd.resolve_action_args

        def _resolve_with_place() -> dict[str, object]:
            kwargs = original_resolve()
            kwargs["place"] = place_a
            return kwargs

        cmd.resolve_action_args = _resolve_with_place
        cmd.func()

        # Alice is in the room, so the pose's own room-wide broadcast
        # (message_location's msg_contents) also lands one entry in
        # `messages` -- filter for the refusal text specifically rather
        # than assuming it's the first call the caller receives.
        refusal_calls = [
            args[0]
            for args, kwargs in messages
            if args and "Bob is across the room" in str(args[0])
        ]
        assert refusal_calls, f"CmdPose never sent the refusal to the caller: {messages}"
        sent_text = str(refusal_calls[0])
        assert "Bob is across the room and will not see table talk." in sent_text
        assert _HINT in sent_text

    def test_pose_at_place_targeting_persona_at_same_place_succeeds(self) -> None:
        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        room_profile = RoomProfileFactory(objectdb=room)
        place = PlaceFactory(room=room_profile, name="the bar")

        char_a = CharacterFactory(db_key="Alice", location=room)
        sheet_a = CharacterSheetFactory(character=char_a)
        PlacePresenceFactory(place=place, persona=sheet_a.primary_persona)

        char_b = CharacterFactory(db_key="Bob", location=room)
        sheet_b = CharacterSheetFactory(character=char_b)
        PlacePresenceFactory(place=place, persona=sheet_b.primary_persona)

        action = PoseAction()
        result = action.run(actor=char_a, text="murmurs to Bob.", targets=[char_b], place=place)

        assert result.success is True
        assert InteractionTargetPersona.objects.filter(persona=sheet_b.primary_persona).exists()


class PoseSubmitViewUnreachableTargetTests(APITestCase):
    """REST-view translation of ``UnreachableError`` into the 400 contract.

    ``PoseSubmitSerializer`` has no ``place``/``receivers`` field today -- the
    live defect (and this fix) is reachable through Place-scoped poses, which on
    the web side only exist via the telnet-parity ``PoseAction`` path covered
    above. This test proves the view's translation of the exception into the
    same ``{code, field, detail, hint}`` shape ``InteractionThreadError`` already
    gets, by raising it at the seam the view calls.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player_data,
            roster_entry=cls.roster_entry,
        )
        cls.identity = CharacterSheetFactory(character=cls.character)
        cls.persona = cls.identity.primary_persona

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        self.room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        self.character.location = self.room
        self.client.force_authenticate(user=self.account)

    def test_submit_pose_translates_unreachable_error_to_400(self) -> None:
        target = PersonaFactory(name="Rowan")
        error = UnreachableError(
            [target],
            _HINT,
            message="Rowan is across the room and will not see table talk.",
        )

        with patch(
            "world.scenes.interaction_views.idempotent_record_interaction",
            side_effect=error,
        ):
            response = self.client.post(
                reverse("interaction-submit-pose"),
                {
                    "client_request_id": str(uuid.uuid4()),
                    "persona_id": self.persona.pk,
                    "content": "murmurs to Rowan.",
                    "target_names": ["Rowan"],
                },
                format="json",
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "target_unreachable"
        assert response.data["field"] == "target_names"
        assert response.data["detail"] == "Rowan is across the room and will not see table talk."
        assert response.data["hint"] == _HINT
