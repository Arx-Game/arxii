"""Tests for MoveToPositionAction and its surfacing in get_player_actions / dispatch_player_action.

Covers:
- (a) get_player_actions: character in a room with positions surfaces a Move option for each
  directly adjacent, currently-passable position.
- (b) get_player_actions: impassable edges are NOT surfaced.
- (c) dispatch_player_action: REGISTRY ref with position_id relocates the character.
- (d) Character not in any position: get_player_actions surfaces no positioning moves (no error).
"""

from __future__ import annotations

import django.test

from actions.constants import ActionBackend
from actions.types import ActionRef
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import (
    connect_positions,
    place_in_position,
    position_of,
)
from world.mechanics.factories import ChallengeInstanceFactory


def _make_character_in_room(room: object) -> object:
    """Create a Character located in room via Evennia's create_object.

    Uses direct ObjectDB creation + raw update to bypass Evennia hooks (the
    DbHolder/setUpTestData idmapper trap from CI shard runs).
    """
    from evennia import create_object

    return create_object(
        "typeclasses.characters.Character",
        key="TestMover",
        location=room,
        nohome=True,
    )


class TestMoveToPositionActionGetPlayerActions(django.test.TestCase):
    """get_player_actions surfaces REGISTRY move options for adjacent passable positions."""

    def setUp(self) -> None:
        from evennia import create_object

        # One room with three positions:
        #   ground (occupied by character) ↔ balcony (open edge, passable)
        #   ground → pit (impassable edge)
        self.room = create_object("typeclasses.rooms.Room", key="TestRoom", nohome=True)
        self.ground = PositionFactory(room=self.room, name="ground")
        self.balcony = PositionFactory(room=self.room, name="balcony")
        self.pit = PositionFactory(room=self.room, name="pit")

        # passable edge: ground ↔ balcony
        self.open_edge = connect_positions(self.ground, self.balcony, is_passable=True)
        # impassable edge: ground ↔ pit
        self.blocked_edge = connect_positions(self.ground, self.pit, is_passable=False)

        # Character placed at ground
        self.character = _make_character_in_room(self.room)
        place_in_position(self.character, self.ground)

    def test_balcony_is_offered_as_move_option(self) -> None:
        """Adjacent passable position (balcony) appears as a REGISTRY PlayerAction."""
        from actions.player_interface import get_player_actions

        actions = get_player_actions(self.character)
        registry_move_actions = [
            a
            for a in actions
            if a.backend == ActionBackend.REGISTRY and a.ref.registry_key == "move_to_position"
        ]
        self.assertTrue(
            len(registry_move_actions) >= 1,
            f"Expected at least 1 move_to_position action, got none. All: {actions}",
        )
        position_ids = {a.ref.position_id for a in registry_move_actions}
        self.assertIn(
            self.balcony.pk,
            position_ids,
            f"Expected balcony (pk={self.balcony.pk}) in offered moves, got: {position_ids}",
        )

    def test_impassable_position_is_not_offered(self) -> None:
        """Impassable adjacent position (pit) is NOT surfaced."""
        from actions.player_interface import get_player_actions

        actions = get_player_actions(self.character)
        registry_move_actions = [
            a
            for a in actions
            if a.backend == ActionBackend.REGISTRY and a.ref.registry_key == "move_to_position"
        ]
        position_ids = {a.ref.position_id for a in registry_move_actions}
        self.assertNotIn(
            self.pit.pk,
            position_ids,
            f"Expected pit (pk={self.pit.pk}) NOT in offered moves, got: {position_ids}",
        )

    def test_unplaced_character_surfaces_no_positioning_moves(self) -> None:
        """A character not in any position gets no move_to_position options (no error)."""
        from evennia import create_object

        from actions.player_interface import get_player_actions

        unplaced = create_object(
            "typeclasses.characters.Character",
            key="Unplaced",
            location=self.room,
            nohome=True,
        )
        actions = get_player_actions(unplaced)
        positioning_actions = [
            a
            for a in actions
            if a.backend == ActionBackend.REGISTRY and a.ref.registry_key == "move_to_position"
        ]
        self.assertEqual(
            len(positioning_actions),
            0,
            f"Expected no positioning moves for unplaced character, got: {positioning_actions}",
        )


class TestMoveToPositionActionDispatch(django.test.TestCase):
    """dispatch_player_action with a move_to_position REGISTRY ref relocates the character."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="DispatchRoom", nohome=True)
        self.ground = PositionFactory(room=self.room, name="ground")
        self.balcony = PositionFactory(room=self.room, name="balcony")
        connect_positions(self.ground, self.balcony, is_passable=True)

        self.character = _make_character_in_room(self.room)
        place_in_position(self.character, self.ground)

    def test_dispatch_moves_character_to_balcony(self) -> None:
        """Dispatching move_to_position with position_id=balcony.pk places character there."""
        from actions.player_interface import dispatch_player_action

        ref = ActionRef(
            backend=ActionBackend.REGISTRY,
            registry_key="move_to_position",
            position_id=self.balcony.pk,
        )
        result = dispatch_player_action(self.character, ref, kwargs={})

        self.assertFalse(result.deferred, "REGISTRY actions should execute immediately")
        self.assertTrue(result.detail.success, f"Move failed: {result.detail.message}")  # type: ignore[union-attr]

        current = position_of(self.character)
        self.assertIsNotNone(current)
        self.assertEqual(
            current.pk,  # type: ignore[union-attr]
            self.balcony.pk,
            f"Expected character at balcony (pk={self.balcony.pk}), got {current}",
        )

    def test_dispatch_to_impassable_position_fails_gracefully(self) -> None:
        """Dispatching move to an impassable-edge position returns failure, not exception."""
        from actions.player_interface import dispatch_player_action

        pit = PositionFactory(room=self.room, name="pit")
        connect_positions(self.ground, pit, is_passable=False)

        ref = ActionRef(
            backend=ActionBackend.REGISTRY,
            registry_key="move_to_position",
            position_id=pit.pk,
        )
        result = dispatch_player_action(self.character, ref, kwargs={})

        # Should not raise; should return a failed ActionResult
        self.assertFalse(result.deferred)
        self.assertFalse(result.detail.success)  # type: ignore[union-attr]


class TestGatedEdgeSurfacing(django.test.TestCase):
    """get_player_actions surfaces gated edges as locked/non-actionable CHALLENGE entries.

    A passable edge with an active gating challenge must appear in the action list
    with prerequisite_met=False and a display name that references the challenge,
    so the player knows the path is blocked and why.
    """

    def setUp(self) -> None:
        from evennia import create_object

        from world.mechanics.factories import (
            ApplicationFactory,
            ChallengeTemplateFactory,
            PropertyFactory,
        )

        self.room = create_object("typeclasses.rooms.Room", key="GatedRoom", nohome=True)
        self.ground = PositionFactory(room=self.room, name="ground_gs")
        self.tower = PositionFactory(room=self.room, name="tower_gs")

        # Wire a gating challenge on the edge.
        prop = PropertyFactory(name="gs_prop")
        ApplicationFactory(target_property=prop)
        template = ChallengeTemplateFactory(name="The Drawbridge")
        self.gate = ChallengeInstanceFactory(
            template=template,
            location=self.room,
            target_object=self.room,
        )
        connect_positions(self.ground, self.tower, gating_challenge=self.gate)

        self.character = _make_character_in_room(self.room)
        place_in_position(self.character, self.ground)

    def test_gated_neighbor_appears_as_locked_entry(self) -> None:
        """A gated adjacent position appears as a CHALLENGE action with prerequisite_met=False."""
        from actions.constants import ActionBackend
        from actions.player_interface import get_player_actions

        actions = get_player_actions(self.character)
        locked = [
            a
            for a in actions
            if a.backend == ActionBackend.CHALLENGE
            and a.ref.challenge_instance_id == self.gate.pk
            and not a.prerequisite_met
        ]
        self.assertEqual(
            len(locked),
            1,
            f"Expected exactly 1 locked gated-edge action, got: {locked}",
        )
        self.assertIn("tower_gs", locked[0].display_name)
        self.assertIn("The Drawbridge", locked[0].display_name)

    def test_gated_edge_not_in_open_move_list(self) -> None:
        """The gated position is NOT offered as a free move_to_position action."""
        from actions.player_interface import get_player_actions

        actions = get_player_actions(self.character)
        open_moves = [
            a
            for a in actions
            if a.backend == ActionBackend.REGISTRY
            and a.ref.registry_key == "move_to_position"
            and a.ref.position_id == self.tower.pk
        ]
        self.assertEqual(
            len(open_moves),
            0,
            "Gated position must not appear as a free move action",
        )

    def test_locked_entry_names_the_challenge(self) -> None:
        """The locked entry's prerequisite_reasons mentions the challenge name."""
        from actions.player_interface import get_player_actions

        actions = get_player_actions(self.character)
        locked = [
            a
            for a in actions
            if a.backend == ActionBackend.CHALLENGE
            and a.ref.challenge_instance_id == self.gate.pk
            and not a.prerequisite_met
        ]
        self.assertEqual(len(locked), 1)
        reasons = locked[0].prerequisite_reasons
        self.assertTrue(
            any("The Drawbridge" in r for r in reasons),
            f"Expected challenge name in prerequisite_reasons, got: {reasons}",
        )
