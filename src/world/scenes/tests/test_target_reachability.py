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

from django.test import TestCase
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
from world.scenes.constants import InteractionMode
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
        """Regression guard for the adaptation this task made to the call site.

        The plain room-heard shape (no place, no explicit receivers, not a
        whisper) is deliberately EXEMPTED from the ``persona_can_receive`` check
        here: that predicate's room-heard branch refuses outright whenever
        ``scene`` is None (it has no room to test presence against -- a
        documented, ratified Task 3 decision, not a bug). But every target
        reaching this function was already resolved via
        ``resolve_characters_by_name(target_names, character.location)``
        upstream, which only ever returns characters at the WRITER'S OWN
        location -- so a room-heard target is guaranteed co-located regardless
        of whether a Scene row exists. Applying the predicate here anyway would
        refuse ordinary scene-less room tagging (an existing, tested REST path
        -- see ``test_submit_pose_with_target_names_creates_target_rows``),
        which is not the defect this task closes.
        """
        writer = PersonaFactory()
        target = PersonaFactory()

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
        assert result.message == "Bob is across the room and will not see table talk."
        assert Interaction.objects.count() == interaction_count
        assert InteractionTargetPersona.objects.count() == target_row_count

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
