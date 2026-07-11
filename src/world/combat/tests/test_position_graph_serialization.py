"""Tests for EncounterDetailSerializer.position_nodes/position_edges (#2006).

Follows the established convention for testing ``EncounterDetailSerializer``
directly in this directory (see ``test_encounter_detail_clashes.py`` /
``test_escalation_serializer_fields.py``): ``to_representation`` unconditionally
recomputes ``is_gm`` from ``request.user.is_authenticated`` (a bare
``RequestFactory`` request has no ``.user`` attribute at all — accessing it
raises ``AttributeError``), so functional coverage goes through a real
authenticated ``APIClient`` request rather than a hand-built serializer
context.

The zero-query warm-path check is scoped to ``position_graph()`` directly
(not the full ``serializer.data``) because ``get_surge_beats`` issues an
unconditional ``DramaticSurgeRecord`` query regardless of prefetch state or
authentication (see ``test_view_query_counts.py``'s query-budget docstring) —
that pre-existing cost is unrelated to this task's prefetch and would make a
full-serializer ``assertNumQueries(0)`` fail for reasons outside this change.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.areas.positioning.factories import PositionEdgeFactory
from world.areas.positioning.services import position_graph
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


class EncounterPositionGraphFieldsTests(TestCase):
    """EncounterDetailSerializer exposes position_nodes/position_edges (#2006)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="posgraph_player")
        cls.character = CharacterFactory(db_key="posgraphchar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=cls.character,
            player_data__account=cls.account,
        )
        cls.scene = SceneFactory()
        SceneParticipationFactory(scene=cls.scene, account=cls.account, is_gm=False)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _get_detail(self, encounter: object) -> dict:
        response = self.client.get(f"/api/combat/{encounter.pk}/")  # type: ignore[attr-defined]
        self.assertEqual(response.status_code, 200)
        return response.data  # type: ignore[return-value]

    def test_position_nodes_and_edges_reflect_the_room_graph(self) -> None:
        edge = PositionEdgeFactory()
        room = edge.position_a.room
        encounter = CombatEncounterFactory(scene=self.scene, room=room)
        CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)

        data = self._get_detail(encounter)

        node_ids = {n["id"] for n in data["position_nodes"]}
        self.assertEqual(node_ids, {edge.position_a_id, edge.position_b_id})
        self.assertEqual(len(data["position_edges"]), 1)
        self.assertEqual(data["position_edges"][0]["position_a_id"], edge.position_a_id)
        self.assertEqual(data["position_edges"][0]["position_b_id"], edge.position_b_id)

    def test_no_room_returns_empty_lists(self) -> None:
        encounter = CombatEncounterFactory(scene=self.scene, room=None)
        CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)

        data = self._get_detail(encounter)

        self.assertEqual(data["position_nodes"], [])
        self.assertEqual(data["position_edges"], [])


class EncounterPositionGraphZeroQueryTests(TestCase):
    """position_graph() reads entirely from the viewset's warm prefetch (#2006)."""

    def test_position_graph_is_zero_query_on_the_warm_combat_path(self) -> None:
        from world.combat.views import CombatEncounterViewSet

        edge = PositionEdgeFactory()
        room = edge.position_a.room
        encounter = CombatEncounterFactory(room=room)

        viewset = CombatEncounterViewSet()
        queryset = viewset._base_queryset().filter(pk=encounter.pk)
        warm_encounter = queryset.get()

        with self.assertNumQueries(0):
            graph = position_graph(warm_encounter.room)

        self.assertEqual({n.id for n in graph.nodes}, {edge.position_a_id, edge.position_b_id})
        self.assertEqual(len(graph.edges), 1)
