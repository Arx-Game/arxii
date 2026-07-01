"""ASCII building map renderer (#670)."""

from world.buildings.map_render import render_building_map
from world.buildings.room_services import dig_room
from world.buildings.tests.test_room_services import RoomBuilderBase, _room_in


class MapRenderTests(RoomBuilderBase):
    def test_header_carries_budget_and_grid_draws_connections(self) -> None:
        dig_room(
            persona=self.owner,
            from_room=self.entry.objectdb,
            direction="north",
            name="Kitchen",
            size=self.snug,
        )
        dig_room(
            persona=self.owner,
            from_room=self.entry.objectdb,
            direction="east",
            name="Study",
            size=self.snug,
        )
        output = render_building_map(self.building, floor=0)
        self.assertIn("Space: 45/100", output)
        self.assertIn("[Entry Hall]", output)
        self.assertIn("[ Kitchen  ]", output)
        self.assertIn("[  Study   ]", output)
        # Kitchen sits north of the entry — vertical connector present.
        self.assertIn("│", output)
        # Study sits east — horizontal connector present.
        self.assertIn("─", output)

    def test_unplaced_rooms_listed(self) -> None:
        _room_in(self.building.area, size=self.snug, name="Cellar")
        output = render_building_map(self.building, floor=0)
        self.assertIn("Unplaced: Cellar", output)

    def test_other_floors_noted(self) -> None:
        dig_room(
            persona=self.owner,
            from_room=self.entry.objectdb,
            direction="up",
            name="Solar",
        )
        output = render_building_map(self.building, floor=0)
        self.assertIn("Other floors: 1", output)
        upstairs = render_building_map(self.building, floor=1)
        self.assertIn("[  Solar   ]", upstairs)
