"""Journeys for the battle map's drawing columns (#4670, slice 1 of #4651).

A staff-authored blueprint place carries the rectangle it is drawn as and its terrain.
Applying the blueprint to a room gives the live place the same four numbers and terrain.
Drawing only: nothing here changes a rule.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from evennia_extensions.factories import MediaFactory, RoomProfileFactory
from world.areas.positioning.factories import MapTerrainFactory
from world.areas.positioning.services import (
    add_blueprint_position,
    create_blueprint,
    instantiate_blueprint,
)


class BlueprintAreaAndTerrainJourneys(TestCase):
    def test_blueprint_place_area_and_terrain_reach_the_live_room(self):
        art = MediaFactory()
        terrain = MapTerrainFactory(name="Wood planks", art=art)
        blueprint = create_blueprint("Tavern")
        bp_pos = add_blueprint_position(blueprint, "Common Room")
        bp_pos.area_x, bp_pos.area_y, bp_pos.area_w, bp_pos.area_h = 2, 2, 8, 9
        bp_pos.terrain = terrain
        bp_pos.save()
        room = RoomProfileFactory().objectdb

        positions = instantiate_blueprint(blueprint, room)

        live = positions[0]
        live.refresh_from_db()
        self.assertEqual((live.area_x, live.area_y, live.area_w, live.area_h), (2, 2, 8, 9))
        self.assertEqual(live.terrain, terrain)
        self.assertEqual(live.terrain.art, art)

    def test_a_partial_area_is_refused(self):
        blueprint = create_blueprint("Cellar")
        bp_pos = add_blueprint_position(blueprint, "Stairs")
        bp_pos.area_x = 1
        with self.assertRaises(IntegrityError), transaction.atomic():
            bp_pos.save()

    def test_a_zero_sized_area_is_refused(self):
        blueprint = create_blueprint("Attic")
        bp_pos = add_blueprint_position(blueprint, "Loft")
        bp_pos.area_x, bp_pos.area_y, bp_pos.area_w, bp_pos.area_h = 1, 1, 0, 3
        with self.assertRaises(IntegrityError), transaction.atomic():
            bp_pos.save()
