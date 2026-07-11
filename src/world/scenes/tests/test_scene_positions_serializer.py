"""Tests for position-related fields added to SceneDetailSerializer (Task 9 / #1017).

Built in setUp rather than setUpTestData: Evennia ObjectDB instances (DbHolder)
are not deepcopyable and would break setUpTestData.
"""

from __future__ import annotations

from django.test import TestCase
from evennia import create_object

from world.areas.positioning.factories import PositionEdgeFactory
from world.areas.positioning.services import (
    connect_positions,
    create_position,
    place_in_position,
)
from world.scenes.factories import InteractionFactory, PersonaFactory, SceneFactory
from world.scenes.serializers import SceneDetailSerializer


class SceneDetailSerializerPositionsTestCase(TestCase):
    """SceneDetailSerializer exposes positions, position_adjacency, persona_positions."""

    def setUp(self) -> None:
        self.room = create_object("typeclasses.rooms.Room", key="PositionTestRoom", nohome=True)

        # 2 positions in the room with 1 connecting edge
        self.pos_a = create_position(self.room, "North Alcove")
        self.pos_b = create_position(self.room, "South Alcove")
        connect_positions(self.pos_a, self.pos_b, is_passable=True)

        # Scene located in the room
        self.scene = SceneFactory(location=self.room)

        # Persona whose character is placed in pos_a
        self.persona = PersonaFactory()
        # The persona's character is persona.character_sheet.character
        character = self.persona.character_sheet.character
        # Move the character into the room so place_in_position can work
        character.location = self.room
        character.save()
        place_in_position(character, self.pos_a)

        # An interaction in the scene by that persona (populates cached_interactions)
        InteractionFactory(scene=self.scene, persona=self.persona)

    def test_positions_has_two_entries(self) -> None:
        """positions field lists both positions in the scene's room."""
        data = SceneDetailSerializer(self.scene).data
        assert len(data["positions"]) == 2

    def test_positions_contain_id_and_name(self) -> None:
        """Each position entry has id and name keys."""
        data = SceneDetailSerializer(self.scene).data
        position_ids = {p["id"] for p in data["positions"]}
        assert self.pos_a.pk in position_ids
        assert self.pos_b.pk in position_ids
        for pos in data["positions"]:
            assert "id" in pos
            assert "name" in pos

    def test_position_adjacency_shows_neighbors(self) -> None:
        """position_adjacency encodes the edge between the two positions."""
        data = SceneDetailSerializer(self.scene).data
        adjacency = {
            entry["position_id"]: entry["adjacent_position_ids"]
            for entry in data["position_adjacency"]
        }
        assert self.pos_a.pk in adjacency
        assert self.pos_b.pk in adjacency
        # Each position lists the other as a neighbor
        assert self.pos_b.pk in adjacency[self.pos_a.pk]
        assert self.pos_a.pk in adjacency[self.pos_b.pk]

    def test_persona_positions_contains_placed_persona(self) -> None:
        """persona_positions includes the persona with its placed position id."""
        data = SceneDetailSerializer(self.scene).data
        persona_positions = data["persona_positions"]
        matching = [pp for pp in persona_positions if pp["persona_id"] == self.persona.pk]
        assert len(matching) == 1
        entry = matching[0]
        assert entry["position"] is not None
        assert entry["position"]["id"] == self.pos_a.pk

    def test_scene_without_location_yields_empty_fields(self) -> None:
        """A scene with location=None returns empty positions/position_adjacency without error."""
        scene_no_location = SceneFactory(location=None)
        data = SceneDetailSerializer(scene_no_location).data
        assert data["positions"] == []
        assert data["position_adjacency"] == []
        assert data["persona_positions"] == []

    def test_persona_whose_character_is_unplaced_yields_null_position(self) -> None:
        """A persona whose character has no ObjectPosition gets position=null."""
        scene = SceneFactory(location=self.room)
        persona_unplaced = PersonaFactory()
        character = persona_unplaced.character_sheet.character
        character.location = self.room
        character.save()
        # Do NOT call place_in_position — character has no ObjectPosition row.
        InteractionFactory(scene=scene, persona=persona_unplaced)
        data = SceneDetailSerializer(scene).data
        persona_entries = [
            pp for pp in data["persona_positions"] if pp["persona_id"] == persona_unplaced.pk
        ]
        assert len(persona_entries) == 1
        assert persona_entries[0]["position"] is None


class ScenePositionGraphFieldsTests(TestCase):
    """SceneDetailSerializer exposes position_nodes/position_edges (#2006)."""

    def test_position_nodes_and_edges_reflect_the_room_graph(self) -> None:
        edge = PositionEdgeFactory()
        scene = SceneFactory(location=edge.position_a.room)

        data = SceneDetailSerializer(scene).data

        node_ids = {n["id"] for n in data["position_nodes"]}
        self.assertEqual(node_ids, {edge.position_a_id, edge.position_b_id})
        self.assertEqual(len(data["position_edges"]), 1)
        self.assertEqual(data["position_edges"][0]["position_a_id"], edge.position_a_id)
        self.assertEqual(data["position_edges"][0]["position_b_id"], edge.position_b_id)

    def test_no_location_returns_empty_lists(self) -> None:
        scene = SceneFactory(location=None)

        data = SceneDetailSerializer(scene).data

        self.assertEqual(data["position_nodes"], [])
        self.assertEqual(data["position_edges"], [])
