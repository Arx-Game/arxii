"""Tests for take_position — voluntary entry onto the position graph (#2005).

Uses setUp (not setUpTestData): Evennia ObjectDB instances (DbHolder) are not
deepcopyable and would break setUpTestData's copy step (see test_aerial.py).
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from world.areas.positioning.constants import PositionKind
from world.areas.positioning.exceptions import PositionError, PositionTransitionError
from world.areas.positioning.services import (
    create_position,
    place_in_position,
    position_of,
    take_position,
)


class TakePositionEligibleKindTests(TestCase):
    """PRIMARY and FEATURE positions are valid voluntary entry points."""

    def setUp(self) -> None:
        from evennia import create_object

        from evennia_extensions.factories import CharacterFactory

        self.room = create_object("typeclasses.rooms.Room", key="TakePosRoom", nohome=True)
        self.primary = create_position(self.room, "throne", kind=PositionKind.PRIMARY)
        self.feature = create_position(self.room, "hearth", kind=PositionKind.FEATURE)
        self.actor = CharacterFactory(location=self.room)

    def test_primary_position_succeeds(self) -> None:
        obj_pos = take_position(self.actor, self.primary)
        self.assertEqual(obj_pos.position_id, self.primary.pk)
        self.assertEqual(position_of(self.actor).pk, self.primary.pk)

    def test_feature_position_succeeds(self) -> None:
        obj_pos = take_position(self.actor, self.feature)
        self.assertEqual(obj_pos.position_id, self.feature.pk)
        self.assertEqual(position_of(self.actor).pk, self.feature.pk)


class TakePositionIneligibleKindTests(TestCase):
    """Non-entry-point kinds (AERIAL/ELEVATED/CHASM/BARRIER_SIDE) reject voluntary entry."""

    def setUp(self) -> None:
        from evennia import create_object

        from evennia_extensions.factories import CharacterFactory

        self.room = create_object("typeclasses.rooms.Room", key="TakePosKindRoom", nohome=True)
        self.actor = CharacterFactory(location=self.room)

    def _assert_kind_rejected(self, kind: str) -> None:
        position = create_position(self.room, f"pos_{kind}", kind=kind)
        with self.assertRaises(PositionError):
            take_position(self.actor, position)
        self.assertIsNone(position_of(self.actor), f"{kind} entry must not place the actor")

    def test_aerial_kind_raises(self) -> None:
        self._assert_kind_rejected(PositionKind.AERIAL)

    def test_elevated_kind_raises(self) -> None:
        self._assert_kind_rejected(PositionKind.ELEVATED)

    def test_chasm_kind_raises(self) -> None:
        self._assert_kind_rejected(PositionKind.CHASM)

    def test_barrier_side_kind_raises(self) -> None:
        self._assert_kind_rejected(PositionKind.BARRIER_SIDE)


class TakePositionAlreadyPlacedTests(TestCase):
    """An actor already placed somewhere must be told to move instead."""

    def setUp(self) -> None:
        from evennia import create_object

        from evennia_extensions.factories import CharacterFactory

        self.room = create_object("typeclasses.rooms.Room", key="TakePosPlacedRoom", nohome=True)
        self.first = create_position(self.room, "first", kind=PositionKind.PRIMARY)
        self.second = create_position(self.room, "second", kind=PositionKind.FEATURE)
        self.actor = CharacterFactory(location=self.room)
        place_in_position(self.actor, self.first)

    def test_already_placed_raises(self) -> None:
        with self.assertRaises(PositionError) as ctx:
            take_position(self.actor, self.second)
        self.assertIn("move", ctx.exception.user_message.lower())
        # The actor must remain at its original position.
        self.assertEqual(position_of(self.actor).pk, self.first.pk)


class TakePositionCrossRoomTests(TestCase):
    """A position in a different room than the actor's location is rejected."""

    def setUp(self) -> None:
        from evennia import create_object

        from evennia_extensions.factories import CharacterFactory

        self.room = create_object("typeclasses.rooms.Room", key="TakePosCrossRoomA", nohome=True)
        self.other_room = create_object(
            "typeclasses.rooms.Room", key="TakePosCrossRoomB", nohome=True
        )
        self.other_position = create_position(
            self.other_room, "elsewhere", kind=PositionKind.PRIMARY
        )
        self.actor = CharacterFactory(location=self.room)

    def test_cross_room_raises(self) -> None:
        with self.assertRaises(PositionError):
            take_position(self.actor, self.other_position)
        self.assertIsNone(position_of(self.actor))


class TakePositionImmobileTests(TestCase):
    """An actor that cannot move (MOVEMENT capability <= 0) cannot voluntarily enter."""

    def setUp(self) -> None:
        from evennia import create_object

        from evennia_extensions.factories import CharacterFactory

        self.room = create_object("typeclasses.rooms.Room", key="TakePosImmobileRoom", nohome=True)
        self.position = create_position(self.room, "spot", kind=PositionKind.PRIMARY)
        self.actor = CharacterFactory(location=self.room)

    def test_immobile_actor_raises(self) -> None:
        with mock.patch("world.areas.positioning.services._can_move", return_value=False):
            with self.assertRaises(PositionTransitionError):
                take_position(self.actor, self.position)
        self.assertIsNone(position_of(self.actor))
