"""Tests for PositionNodeBase and PositionEdgeBase abstract model contracts.

Validates that the abstract bases expose the expected fields and that
_validate_canonical enforces self-loop and canonical-order invariants.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.areas.positioning.constants import PositionKind
from world.areas.positioning.models import (
    Position,
    PositionEdge,
    PositionEdgeBase,
    PositionNodeBase,
)


class PositionNodeBaseInheritanceTests(TestCase):
    """Position correctly inherits from PositionNodeBase."""

    def test_position_is_subclass_of_node_base(self) -> None:
        self.assertTrue(issubclass(Position, PositionNodeBase))

    def test_node_base_is_abstract(self) -> None:
        self.assertTrue(PositionNodeBase._meta.abstract)

    def test_position_has_name_field(self) -> None:
        field = Position._meta.get_field("name")
        self.assertEqual(field.max_length, 50)

    def test_position_has_kind_field_with_correct_default(self) -> None:
        field = Position._meta.get_field("kind")
        self.assertEqual(field.default, PositionKind.FEATURE)
        self.assertEqual(field.max_length, 20)

    def test_position_has_description_field_blank(self) -> None:
        field = Position._meta.get_field("description")
        self.assertTrue(field.blank)


class PositionEdgeBaseInheritanceTests(TestCase):
    """PositionEdge correctly inherits from PositionEdgeBase."""

    def test_position_edge_is_subclass_of_edge_base(self) -> None:
        self.assertTrue(issubclass(PositionEdge, PositionEdgeBase))

    def test_edge_base_is_abstract(self) -> None:
        self.assertTrue(PositionEdgeBase._meta.abstract)

    def test_position_edge_has_is_passable_field_defaulting_true(self) -> None:
        field = PositionEdge._meta.get_field("is_passable")
        self.assertTrue(field.default)


class ValidateCanonicalTests(TestCase):
    """PositionEdgeBase._validate_canonical enforces self-loop and pk-order."""

    def test_self_loop_raises(self) -> None:
        with self.assertRaises(ValidationError):
            PositionEdgeBase._validate_canonical(5, 5)

    def test_reversed_order_raises(self) -> None:
        with self.assertRaises(ValidationError):
            PositionEdgeBase._validate_canonical(10, 3)

    def test_correct_order_passes(self) -> None:
        # Must not raise
        PositionEdgeBase._validate_canonical(1, 2)

    def test_none_a_skipped(self) -> None:
        # None inputs are skipped (partial object not yet saved)
        PositionEdgeBase._validate_canonical(None, 5)

    def test_none_b_skipped(self) -> None:
        PositionEdgeBase._validate_canonical(5, None)

    def test_both_none_skipped(self) -> None:
        PositionEdgeBase._validate_canonical(None, None)


class PositionEdgeCleanTests(TestCase):
    """PositionEdge.clean() delegates to _validate_canonical + same-room check."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room1 = create_object("typeclasses.rooms.Room", key="CleanRoom1", nohome=True)
        self.room2 = create_object("typeclasses.rooms.Room", key="CleanRoom2", nohome=True)
        self.pos_a = Position.objects.create(room=self.room1, name="clean_a")
        self.pos_b = Position.objects.create(room=self.room1, name="clean_b")
        self.pos_c = Position.objects.create(room=self.room2, name="clean_c")

    def _make_edge(self, a: Position, b: Position) -> PositionEdge:
        edge = PositionEdge(position_a=a, position_b=b)
        edge.position_a_id = a.pk
        edge.position_b_id = b.pk
        return edge

    def test_clean_passes_for_valid_same_room_edge(self) -> None:
        # Ensure a < b ordering
        if self.pos_a.pk < self.pos_b.pk:
            edge = self._make_edge(self.pos_a, self.pos_b)
        else:
            edge = self._make_edge(self.pos_b, self.pos_a)
        edge.clean()  # must not raise

    def test_clean_raises_for_cross_room_edge(self) -> None:
        # Endpoints are in different rooms; full_clean must raise regardless of which is
        # position_a. Explicitly order by pk to ensure deterministic assignment.
        endpoints = sorted([self.pos_a, self.pos_c], key=lambda p: p.pk)
        edge = PositionEdge(position_a=endpoints[0], position_b=endpoints[1])
        edge.position_a_id = endpoints[0].pk
        edge.position_b_id = endpoints[1].pk
        with self.assertRaises(ValidationError):
            edge.clean()


class ElevationAnchorTests(TestCase):
    """Position.elevation_anchor self-FK and PositionKind.CHASM."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia import create_object

        cls.room = create_object("typeclasses.rooms.Room", key="ElevRoom1", nohome=True)

    def test_chasm_kind_exists(self) -> None:
        self.assertEqual(PositionKind.CHASM, "chasm")

    def test_elevation_anchor_links_below(self) -> None:
        ground = Position.objects.create(room=self.room, name="ledge", kind=PositionKind.PRIMARY)
        aloft = Position.objects.create(
            room=self.room,
            name="above ledge",
            kind=PositionKind.AERIAL,
            elevation_anchor=ground,
        )
        self.assertEqual(aloft.elevation_anchor_id, ground.pk)
        self.assertIn(aloft, ground.elevated_over.all())

    def test_elevation_anchor_nullable_for_ground(self) -> None:
        ground = Position.objects.create(room=self.room, name="floor", kind=PositionKind.PRIMARY)
        self.assertIsNone(ground.elevation_anchor_id)


class BlueprintEdgeGatingTemplateTests(TestCase):
    def test_gating_challenge_template_defaults_to_none(self) -> None:
        from world.areas.positioning.factories import BlueprintEdgeFactory

        edge = BlueprintEdgeFactory()
        self.assertIsNone(edge.gating_challenge_template_id)

    def test_gating_challenge_template_can_be_set(self) -> None:
        from world.areas.positioning.factories import BlueprintEdgeFactory
        from world.mechanics.factories import ChallengeTemplateFactory

        template = ChallengeTemplateFactory()
        edge = BlueprintEdgeFactory(gating_challenge_template=template)
        self.assertEqual(edge.gating_challenge_template_id, template.pk)
