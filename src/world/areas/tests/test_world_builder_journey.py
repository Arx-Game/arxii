"""Journey test: canvas verbs end-to-end into the grid-export pipeline (#2449).

Exercises the staff world-builder canvas at the service layer (no HTTP): stand
up an AUTHORED area, dig two rooms, link them, reposition one via the canvas
drag verb, and re-promote the other (idempotent) — then run the slice-1
exporter (``core_management.grid_export.export_grid_bundles``) and assert the
resulting bundle carries everything the canvas wrote. This is the one test
that proves the eleven ``world_builder`` actions actually feed the existing
export pipeline, not just their own per-action unit assertions
(``actions/tests/test_world_builder_actions.py``).
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

from django.test import TestCase

from actions.definitions.world_builder import (
    CreateAreaAction,
    PromoteRoomAction,
    StaffDigRoomAction,
    StaffLinkRoomsAction,
    StaffPlaceRoomAction,
)
from core_management.grid_export import export_grid_bundles
from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import RoomProfile
from world.areas.constants import AreaLevel
from world.areas.models import Area
from world.character_sheets.factories import CharacterSheetFactory


def _staff_actor(db_key: str):
    """A Character whose account is staff, with a working CharacterSheet+persona.

    Mirrors ``actions/tests/test_world_builder_actions.py``'s helper — the
    canvas gate is account-level (``StaffOnlyPrerequisite``), not GM-ladder
    (that's deferred to #2450).
    """
    char = CharacterFactory(db_key=db_key)
    account = AccountFactory(username=f"acct_{db_key}", is_staff=True)
    char.db_account = account
    char.save()
    CharacterSheetFactory(character=char)
    return char


class WorldBuilderJourneyTests(TestCase):
    """create_area -> staff_dig_room x2 -> staff_link_rooms -> staff_place_room
    -> promote_room -> export_grid_bundles, asserting the bundle is complete."""

    def setUp(self) -> None:
        self.staff = _staff_actor("WorldBuilderJourneyStaff")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.content_root = Path(self.tmp.name)

    def _load_bundle(self, slug: str) -> dict:
        path = self.content_root / "fixtures" / "grid" / f"{slug}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_canvas_verbs_feed_the_grid_exporter(self) -> None:
        # 1. create_area — AUTHORED with a slug from the moment it's created.
        create_result = CreateAreaAction().run(
            self.staff, name="Journey Ward", slug="journey-ward", level=int(AreaLevel.WARD)
        )
        assert create_result.success, create_result.message
        area = Area.objects.get(slug="journey-ward")

        # 2. staff_dig_room x2 — both land as AUTHORED with suggested fixture keys.
        dig_one = StaffDigRoomAction().run(
            self.staff, area_id=area.pk, name="Room One", grid_x=0, grid_y=0
        )
        assert dig_one.success, dig_one.message
        dig_two = StaffDigRoomAction().run(
            self.staff, area_id=area.pk, name="Room Two", grid_x=1, grid_y=0
        )
        assert dig_two.success, dig_two.message
        room_one = RoomProfile.objects.get(fixture_key="journey-ward/room-one")
        room_two = RoomProfile.objects.get(fixture_key="journey-ward/room-two")

        # 3. staff_link_rooms — a named exit pair between them.
        link_result = StaffLinkRoomsAction().run(
            self.staff,
            room_a_id=room_one.objectdb_id,
            room_b_id=room_two.objectdb_id,
            name_ab="East Door",
            name_ba="West Door",
        )
        assert link_result.success, link_result.message

        # 4. staff_place_room — the canvas drag verb, cosmetic re-placement.
        place_result = StaffPlaceRoomAction().run(
            self.staff, room_id=room_one.objectdb_id, grid_x=5, grid_y=7
        )
        assert place_result.success, place_result.message

        # 5. promote_room — re-promoting with the same fixture_key is a no-op
        # success (ADR-0138 key permanence); proves the promote verb is wired
        # even though staff_dig_room already authored the room outright.
        promote_result = PromoteRoomAction().run(
            self.staff, room_id=room_two.objectdb_id, fixture_key=room_two.fixture_key
        )
        assert promote_result.success, promote_result.message

        # 6. export_grid_bundles — the slice-1 pipeline should now see it all.
        result = export_grid_bundles(self.content_root)
        assert not result.errors
        assert result.room_count == 2
        assert area.slug in {p.stem for p in result.written}

        bundle = self._load_bundle("journey-ward")
        assert bundle["area"]["slug"] == "journey-ward"
        assert bundle["area"]["name"] == "Journey Ward"

        rooms_by_key = {r["fixture_key"]: r for r in bundle["rooms"]}
        assert set(rooms_by_key) == {"journey-ward/room-one", "journey-ward/room-two"}
        assert rooms_by_key["journey-ward/room-one"]["grid_x"] == 5
        assert rooms_by_key["journey-ward/room-one"]["grid_y"] == 7
        assert rooms_by_key["journey-ward/room-two"]["grid_x"] == 1
        assert rooms_by_key["journey-ward/room-two"]["grid_y"] == 0

        exits_by_key = {(e["source"], e["key"]): e for e in bundle["exits"]}
        east = exits_by_key[("journey-ward/room-one", "East Door")]
        assert east["destination"] == "journey-ward/room-two"
        west = exits_by_key[("journey-ward/room-two", "West Door")]
        assert west["destination"] == "journey-ward/room-one"
