"""Tests for TakePositionAction and its surfacing in get_player_actions (#2005).

Covers:
- (a) get_player_actions: an unplaced actor in a staged room (has PRIMARY/FEATURE
  positions) surfaces one take_position PlayerAction per entry-kind position.
- (b) get_player_actions: a placed actor's move_to_position options are unchanged
  (no take_position options appear).
- (c) get_player_actions: an unplaced actor in an unstaged room (no positions at
  all) surfaces no take_position options.
- (d) dispatch_player_action / TakePositionAction.run: success + failure paths.
"""

from __future__ import annotations

import django.test

from actions.constants import ActionBackend
from actions.types import ActionRef
from world.areas.positioning.constants import PositionKind
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import connect_positions, place_in_position, position_of


def _make_character_in_room(room: object) -> object:
    """Create a Character located in room via Evennia's create_object."""
    from evennia import create_object

    return create_object(
        "typeclasses.characters.Character",
        key="TestTaker",
        location=room,
        nohome=True,
    )


class TestTakePositionPicker(django.test.TestCase):
    """get_player_actions surfaces take_position options for unplaced actors."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="TakePosPickerRoom", nohome=True)
        self.throne = PositionFactory(room=self.room, name="throne", kind=PositionKind.PRIMARY)
        self.hearth = PositionFactory(room=self.room, name="hearth", kind=PositionKind.FEATURE)
        # AERIAL kind must never be offered as a voluntary entry point.
        self.sky = PositionFactory(room=self.room, name="sky", kind=PositionKind.AERIAL)

    def test_unplaced_actor_offered_one_action_per_entry_position(self) -> None:
        from actions.player_interface import get_player_actions

        actor = _make_character_in_room(self.room)
        actions = get_player_actions(actor)
        take_actions = [
            a
            for a in actions
            if a.backend == ActionBackend.REGISTRY and a.ref.registry_key == "take_position"
        ]
        position_ids = {a.ref.position_id for a in take_actions}
        self.assertEqual(
            position_ids,
            {self.throne.pk, self.hearth.pk},
            f"Expected throne+hearth take_position options, got: {take_actions}",
        )

    def test_placed_actor_gets_no_take_position_options(self) -> None:
        """A placed actor sees move options, not take_position options."""
        from actions.player_interface import get_player_actions

        actor = _make_character_in_room(self.room)
        connect_positions(self.throne, self.hearth, is_passable=True)
        place_in_position(actor, self.throne)

        actions = get_player_actions(actor)
        take_actions = [
            a
            for a in actions
            if a.backend == ActionBackend.REGISTRY and a.ref.registry_key == "take_position"
        ]
        move_actions = [
            a
            for a in actions
            if a.backend == ActionBackend.REGISTRY and a.ref.registry_key == "move_to_position"
        ]
        self.assertEqual(take_actions, [])
        move_position_ids = {a.ref.position_id for a in move_actions}
        self.assertIn(self.hearth.pk, move_position_ids)

    def test_unstaged_room_offers_no_take_position_options(self) -> None:
        """A room with no positions at all surfaces no take_position options."""
        from evennia import create_object

        from actions.player_interface import get_player_actions

        bare_room = create_object("typeclasses.rooms.Room", key="BareRoom", nohome=True)
        actor = _make_character_in_room(bare_room)

        actions = get_player_actions(actor)
        take_actions = [
            a
            for a in actions
            if a.backend == ActionBackend.REGISTRY and a.ref.registry_key == "take_position"
        ]
        self.assertEqual(take_actions, [])


class TestTakePositionActionDispatch(django.test.TestCase):
    """dispatch_player_action with a take_position REGISTRY ref places the actor."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="TakePosDispatchRoom", nohome=True)
        self.throne = PositionFactory(room=self.room, name="throne_d", kind=PositionKind.PRIMARY)
        self.sky = PositionFactory(room=self.room, name="sky_d", kind=PositionKind.AERIAL)
        self.actor = _make_character_in_room(self.room)

    def test_dispatch_places_actor_at_entry_position(self) -> None:
        from actions.player_interface import dispatch_player_action

        ref = ActionRef(
            backend=ActionBackend.REGISTRY,
            registry_key="take_position",
            position_id=self.throne.pk,
        )
        result = dispatch_player_action(self.actor, ref, kwargs={})

        self.assertFalse(result.deferred)
        detail = result.detail
        self.assertTrue(detail.success, f"Take position failed: {detail.message}")  # type: ignore[union-attr]
        current = position_of(self.actor)
        self.assertIsNotNone(current)
        self.assertEqual(current.pk, self.throne.pk)  # type: ignore[union-attr]

    def test_dispatch_to_non_entry_kind_fails_gracefully(self) -> None:
        from actions.player_interface import dispatch_player_action

        ref = ActionRef(
            backend=ActionBackend.REGISTRY,
            registry_key="take_position",
            position_id=self.sky.pk,
        )
        result = dispatch_player_action(self.actor, ref, kwargs={})

        self.assertFalse(result.deferred)
        self.assertFalse(result.detail.success)  # type: ignore[union-attr]
        self.assertIsNone(position_of(self.actor))

    def test_dispatch_already_placed_fails_gracefully(self) -> None:
        from actions.player_interface import dispatch_player_action

        place_in_position(self.actor, self.throne)
        other = PositionFactory(room=self.room, name="other_d", kind=PositionKind.FEATURE)
        ref = ActionRef(
            backend=ActionBackend.REGISTRY,
            registry_key="take_position",
            position_id=other.pk,
        )
        result = dispatch_player_action(self.actor, ref, kwargs={})

        self.assertFalse(result.deferred)
        self.assertFalse(result.detail.success)  # type: ignore[union-attr]
        self.assertIn("move", result.detail.message.lower())  # type: ignore[union-attr]
