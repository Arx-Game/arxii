"""Tests for the reachability predicate (#3787 decision 3).

Each case below breaks the invariant it proves: the "not reachable" tests
construct a persona genuinely outside the venue and assert the refusal,
rather than only checking the happy path still passes.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import InteractionMode, InteractionVisibility
from world.scenes.factories import (
    InteractionFactory,
    PersonaFactory,
    PlaceFactory,
    PlacePresenceFactory,
    SceneFactory,
)
from world.scenes.models import Interaction
from world.scenes.reachability import UnreachableError, persona_can_receive


def _persona_at(room) -> object:
    """Build a Persona whose character is physically located in ``room``."""
    character = CharacterFactory(location=room)
    sheet = CharacterSheetFactory(character=character)
    return PersonaFactory(character_sheet=sheet)


class TestPersonaCanReceiveRoomHeard(TestCase):
    """Room-heard shape: no place, no receivers, not a whisper."""

    def test_persona_present_in_room_is_reachable(self) -> None:
        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        scene = SceneFactory(location=room)
        persona = _persona_at(room)

        assert persona_can_receive(
            persona,
            scene=scene,
            place=None,
            receivers=None,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_persona_elsewhere_is_not_reachable(self) -> None:
        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        other_room = ObjectDBFactory(db_key="Cellar", db_typeclass_path="typeclasses.rooms.Room")
        scene = SceneFactory(location=room)
        persona = _persona_at(other_room)

        assert not persona_can_receive(
            persona,
            scene=scene,
            place=None,
            receivers=None,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_no_scene_is_not_reachable(self) -> None:
        # No room to test presence against - reachability cannot be confirmed,
        # so the predicate refuses rather than guessing.
        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        persona = _persona_at(room)

        assert not persona_can_receive(
            persona,
            scene=None,
            place=None,
            receivers=None,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_escalated_to_very_private_is_not_reachable_even_when_present(self) -> None:
        """Breaks the invariant: a persona standing right in the room, refused.

        Mirrors ``mark_very_private`` escalating a plain receiver-less broadcast
        pose (same shape: place=None, receivers=None, not a whisper) to
        VERY_PRIVATE with no change to place/receivers. ``visible_to`` then
        refuses this row to EVERYONE, staff included (#1219) - reachability
        must agree, not just presence-check the shape.
        """
        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        scene = SceneFactory(location=room)
        persona = _persona_at(room)

        assert not persona_can_receive(
            persona,
            scene=scene,
            place=None,
            receivers=None,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.VERY_PRIVATE,
        )

    def test_escalated_to_perceived_only_is_not_reachable_even_when_present(self) -> None:
        """Same break as VERY_PRIVATE: PERCEIVED_ONLY also fails ``visibility=DEFAULT``,

        so ``visible_to`` never treats a receiver-less PERCEIVED_ONLY row as
        room-heard either - it reaches only the writer's own account, staff, and
        the scene's GM (a log-read exception this predicate deliberately does
        not mirror; see the module docstring).
        """
        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        scene = SceneFactory(location=room)
        persona = _persona_at(room)

        assert not persona_can_receive(
            persona,
            scene=scene,
            place=None,
            receivers=None,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.PERCEIVED_ONLY,
        )


class TestPersonaCanReceivePlaceScoped(TestCase):
    """Place-scoped shape: reachability is PlacePresence, never the room at large."""

    def test_persona_at_different_place_is_not_reachable(self) -> None:
        room = RoomProfileFactory()
        place = PlaceFactory(room=room, name="the bar")
        other_place = PlaceFactory(room=room, name="the hearth")
        persona = PersonaFactory()
        PlacePresenceFactory(place=other_place, persona=persona)

        assert not persona_can_receive(
            persona,
            scene=None,
            place=place,
            receivers=None,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_persona_at_same_place_is_reachable(self) -> None:
        room = RoomProfileFactory()
        place = PlaceFactory(room=room, name="the bar")
        persona = PersonaFactory()
        PlacePresenceFactory(place=place, persona=persona)

        assert persona_can_receive(
            persona,
            scene=None,
            place=place,
            receivers=None,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_persona_at_place_but_not_an_explicit_receiver_is_not_reachable(self) -> None:
        # A Place row may ALSO narrow to a specific listener (a private aside at
        # the table) - being physically present is necessary but not sufficient.
        room = RoomProfileFactory()
        place = PlaceFactory(room=room, name="the bar")
        persona = PersonaFactory()
        other_persona = PersonaFactory()
        PlacePresenceFactory(place=place, persona=persona)

        assert not persona_can_receive(
            persona,
            scene=None,
            place=place,
            receivers=[other_persona.pk],
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_place_scoped_reachability_is_unaffected_by_escalated_visibility(self) -> None:
        # A Place-scoped row is never room_heard in visible_to regardless of
        # visibility (place__isnull=True is required either way), so escalating
        # it changes only who may read the log afterward, not who was ever the
        # live audience - PlacePresence keeps deciding this branch.
        room = RoomProfileFactory()
        place = PlaceFactory(room=room, name="the bar")
        persona = PersonaFactory()
        PlacePresenceFactory(place=place, persona=persona)

        assert persona_can_receive(
            persona,
            scene=None,
            place=place,
            receivers=None,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.VERY_PRIVATE,
        )


class TestPersonaCanReceiveWhisper(TestCase):
    """Whisper shape: reachable only for the named party, regardless of location."""

    def test_persona_outside_whisper_party_is_not_reachable(self) -> None:
        party_persona = PersonaFactory()
        outsider = PersonaFactory()

        assert not persona_can_receive(
            outsider,
            scene=None,
            place=None,
            receivers=[party_persona.pk],
            mode=InteractionMode.WHISPER,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_persona_in_whisper_party_is_reachable(self) -> None:
        party_persona = PersonaFactory()

        assert persona_can_receive(
            party_persona,
            scene=None,
            place=None,
            receivers=[party_persona.pk],
            mode=InteractionMode.WHISPER,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_whisper_with_no_receivers_is_not_reachable(self) -> None:
        persona = PersonaFactory()

        assert not persona_can_receive(
            persona,
            scene=None,
            place=None,
            receivers=None,
            mode=InteractionMode.WHISPER,
            visibility=InteractionVisibility.DEFAULT,
        )


class TestPersonaCanReceiveDirectedReceivers(TestCase):
    """Explicit receivers without a Place: a targeted mutter in the open room."""

    def test_persona_not_in_receiver_list_is_not_reachable(self) -> None:
        receiver = PersonaFactory()
        outsider = PersonaFactory()

        assert not persona_can_receive(
            outsider,
            scene=None,
            place=None,
            receivers=[receiver.pk],
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_persona_in_receiver_list_is_reachable(self) -> None:
        receiver = PersonaFactory()

        assert persona_can_receive(
            receiver,
            scene=None,
            place=None,
            receivers=[receiver.pk],
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_receivers_accepts_persona_instances_not_just_ids(self) -> None:
        receiver = PersonaFactory()

        assert persona_can_receive(
            receiver,
            scene=None,
            place=None,
            receivers=[receiver],
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_directed_receivers_reachability_is_unaffected_by_escalated_visibility(self) -> None:
        # Same reasoning as the Place case: receivers__isnull=False already
        # excludes this shape from room_heard in visible_to, so the recorded
        # receiver row keeps deciding this branch regardless of visibility.
        receiver = PersonaFactory()

        assert persona_can_receive(
            receiver,
            scene=None,
            place=None,
            receivers=[receiver.pk],
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.VERY_PRIVATE,
        )


class TestEmptyReceiversMeansNoExplicitReceivers(TestCase):
    """An explicit ``receivers=[]`` reads as broadcast, not as "nobody".

    ``create_interaction`` treats ``[]`` as falsy and writes no
    ``InteractionReceiver`` rows, so the row it persists IS room-heard. Normalizing
    ``[]`` to an empty frozenset instead made this predicate refuse every persona for
    exactly that row, so the two disagreed about one value.
    """

    def test_room_heard_persona_is_reachable_with_an_empty_receiver_list(self) -> None:
        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        scene = SceneFactory(location=room)
        persona = _persona_at(room)

        assert persona_can_receive(
            persona,
            scene=scene,
            place=None,
            receivers=[],
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_empty_receiver_list_still_refuses_a_persona_who_is_elsewhere(self) -> None:
        """The normalization widens nothing: room-heard presence still decides."""
        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        cellar = ObjectDBFactory(db_key="Cellar", db_typeclass_path="typeclasses.rooms.Room")
        scene = SceneFactory(location=room)
        persona = _persona_at(cellar)

        assert not persona_can_receive(
            persona,
            scene=scene,
            place=None,
            receivers=[],
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_place_scoped_row_with_an_empty_receiver_list_needs_only_presence(self) -> None:
        place = PlaceFactory()
        persona = PersonaFactory()
        PlacePresenceFactory(place=place, persona=persona)

        assert persona_can_receive(
            persona,
            scene=None,
            place=place,
            receivers=[],
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_whisper_with_an_empty_receiver_list_is_still_reachable_by_nobody(self) -> None:
        """A whisper is directed by construction, so an empty party reaches no one."""
        persona = PersonaFactory()

        assert not persona_can_receive(
            persona,
            scene=None,
            place=None,
            receivers=[],
            mode=InteractionMode.WHISPER,
            visibility=InteractionVisibility.DEFAULT,
        )


class TestUnreachableError(TestCase):
    def test_carries_personas_and_venue_hint(self) -> None:
        persona = PersonaFactory()

        error = UnreachableError([persona], "Leave the bar to answer this.")

        assert error.personas == [persona]
        assert error.venue_hint == "Leave the bar to answer this."
        assert str(error) == "Leave the bar to answer this."


class TestAgreesWithVisibleTo(TestCase):
    """Pins agreement between ``persona_can_receive`` and ``visible_to`` for a
    non-staff, non-participant, physically-present viewer - the case where a
    live-presence answer and a log-read-access answer should land the same way.

    This is the drift guard the room-heard visibility bug slipped through: both
    predicates are exercised against the SAME persisted ``Interaction`` row for
    each shape, including an escalated-visibility case.
    """

    def _present_persona_and_scene(self):
        room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        scene = SceneFactory(location=room)
        persona = _persona_at(room)
        return persona, scene

    def test_default_room_heard_pose_agrees(self) -> None:
        persona, scene = self._present_persona_and_scene()
        writer_account = AccountFactory()
        interaction = InteractionFactory(
            scene=scene,
            writer_account=writer_account,
            visibility=InteractionVisibility.DEFAULT,
        )
        viewer_account = AccountFactory()

        reachable = persona_can_receive(
            persona,
            scene=scene,
            place=interaction.place,
            receivers=None,
            mode=interaction.mode,
            visibility=interaction.visibility,
        )
        readable = (
            Interaction.objects.visible_to(viewer_account, persona_ids=[persona.pk])
            .filter(pk=interaction.pk, timestamp=interaction.timestamp)
            .exists()
        )

        assert reachable is True
        assert readable is True
        assert reachable == readable

    def test_escalated_very_private_pose_agrees(self) -> None:
        """The exact shape the fix round 1 finding described.

        A receiver-less broadcast pose escalated to VERY_PRIVATE: ``visible_to``
        refuses it to a present-but-uninvolved viewer (not staff, not the
        writer's own account, no GM row) - reachability must refuse it too,
        even though the persona is standing right in the room.
        """
        persona, scene = self._present_persona_and_scene()
        writer_account = AccountFactory()
        interaction = InteractionFactory(
            scene=scene,
            writer_account=writer_account,
            visibility=InteractionVisibility.VERY_PRIVATE,
        )
        viewer_account = AccountFactory()

        reachable = persona_can_receive(
            persona,
            scene=scene,
            place=interaction.place,
            receivers=None,
            mode=interaction.mode,
            visibility=interaction.visibility,
        )
        readable = (
            Interaction.objects.visible_to(viewer_account, persona_ids=[persona.pk])
            .filter(pk=interaction.pk, timestamp=interaction.timestamp)
            .exists()
        )

        assert reachable is False
        assert readable is False
        assert reachable == readable

    def test_staff_read_exception_is_a_deliberate_divergence_not_a_bug(self) -> None:
        """The one intended difference: staff reads escalated PERCEIVED_ONLY;

        reachability refuses everyone. Documented, not silently omitted (see
        the module docstring's "Deliberate divergence" section) - staff/GM read
        access is an administrative permission, not a claim about where anyone
        is standing.
        """
        persona, scene = self._present_persona_and_scene()
        writer_account = AccountFactory()
        interaction = InteractionFactory(
            scene=scene,
            writer_account=writer_account,
            visibility=InteractionVisibility.PERCEIVED_ONLY,
        )
        staff_account = AccountFactory(is_staff=True)

        reachable = persona_can_receive(
            persona,
            scene=scene,
            place=interaction.place,
            receivers=None,
            mode=interaction.mode,
            visibility=interaction.visibility,
        )
        staff_can_read = (
            Interaction.objects.visible_to(staff_account, persona_ids=[persona.pk])
            .filter(pk=interaction.pk, timestamp=interaction.timestamp)
            .exists()
        )

        assert reachable is False
        assert staff_can_read is True
        assert reachable != staff_can_read
