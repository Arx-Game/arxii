"""Staff-only world-builder read API (#2449 Task 4).

The staff canvas's read surface: the area tree (``WorldBuilderViewSet.list``)
and the per-area manager payload (``.manager``) — all rooms in the area
(private included) plus their cross-area-visible exits. Gated by
``IsAdminUser`` alone (no ownership/tenancy standing — this is staff
tooling), unlike the player-facing ``AreaViewSet``/``BuildingManagerViewSet``.
"""

from django.test import tag
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from evennia_extensions.models import ObjectDisplayData, RoomProfile
from world.areas.constants import AreaLevel, GridOrigin
from world.areas.factories import AreaFactory
from world.areas.grid_services import create_exit_pair


def _room_in(area, *, name="A Room", **profile_kwargs):
    room = ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.rooms.Room")
    RoomProfile.objects.update_or_create(
        objectdb=room,
        defaults={"area": area, **profile_kwargs},
    )
    return room


@tag("postgres")  # Area.save() refreshes the areas_areaclosure materialized view
class WorldBuilderApiBase(APITestCase):
    # Fixtures live in setUp, NOT setUpTestData — Evennia typeclass objects
    # carry an un-deepcopyable DbHolder once their attribute handler attaches
    # (see world.buildings.tests.test_manager_api for the same note).
    def setUp(self) -> None:
        self.staff_account = AccountFactory(username="staff_one", is_staff=True)
        self.player_account = AccountFactory(username="player_one", is_staff=False)

        self.area = AreaFactory(
            level=AreaLevel.WARD, name="Golden Ward", origin=GridOrigin.AUTHORED, slug="golden-ward"
        )
        self.other_area = AreaFactory(level=AreaLevel.WARD, name="Ashen Row")

        self.public_room = _room_in(
            self.area,
            name="Market Square",
            is_public=True,
            is_social_hub=True,
            grid_x=0,
            grid_y=0,
            floor=0,
            fixture_key="golden-ward/market-square",
            origin=GridOrigin.AUTHORED,
        )
        self.private_room = _room_in(
            self.area,
            name="Backroom",
            is_public=False,
            grid_x=1,
            grid_y=0,
            floor=0,
        )
        self.foreign_room = _room_in(self.other_area, name="Ashen Gate")

        ObjectDisplayData.objects.create(
            object=self.public_room, permanent_description="A bustling market square."
        )

        # Intra-area exit pair.
        self.exit_out, self.exit_back = create_exit_pair(
            name="north",
            aliases=(),
            reverse_name="south",
            reverse_aliases=(),
            room_a=self.public_room,
            room_b=self.private_room,
        )
        # Cross-area exit, one-way (portal-style): public_room -> foreign_room.
        self.cross_exit = ObjectDBFactory(
            db_key="portal",
            db_typeclass_path="typeclasses.exits.Exit",
            location=self.public_room,
            destination=self.foreign_room,
        )
        # An exit whose *location* is the foreign area — must not leak into
        # this area's manager payload (exits_from_rooms only sees the
        # requested area's own rooms as a source).
        self.foreign_exit = ObjectDBFactory(
            db_key="return-portal",
            db_typeclass_path="typeclasses.exits.Exit",
            location=self.foreign_room,
            destination=self.public_room,
        )

        # An occupant in the private room.
        self.occupant = CharacterFactory(db_key="Lurker")
        self.occupant.move_to(self.private_room, quiet=True, move_type="teleport")

    def _get(self, url, account, **params):
        if account is not None:
            self.client.force_authenticate(user=account)
        return self.client.get(url, params)


class WorldBuilderAreaListTests(WorldBuilderApiBase):
    def _url(self) -> str:
        return "/api/world-builder/areas/"

    def test_anonymous_rejected(self) -> None:
        response = self.client.get(self._url())
        self.assertIn(
            response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_non_staff_rejected(self) -> None:
        response = self._get(self._url(), self.player_account)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_sees_area_tree_with_pagination(self) -> None:
        response = self._get(self._url(), self.staff_account)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertIn("count", response.data)
        names = {row["name"] for row in response.data["results"]}
        self.assertIn(self.area.name, names)
        row = next(row for row in response.data["results"] if row["id"] == self.area.pk)
        self.assertEqual(row["slug"], "golden-ward")
        self.assertEqual(row["origin"], GridOrigin.AUTHORED)
        self.assertIsNone(row["parent"])
        self.assertEqual(row["children_count"], 0)

    def test_filter_by_parent(self) -> None:
        child = AreaFactory(level=AreaLevel.NEIGHBORHOOD, name="Child Row", parent=self.area)
        response = self._get(self._url(), self.staff_account, parent=self.area.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {child.pk})

    def test_filter_has_parent(self) -> None:
        child = AreaFactory(level=AreaLevel.NEIGHBORHOOD, name="Child Row 2", parent=self.area)
        response = self._get(self._url(), self.staff_account, has_parent=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(child.pk, ids)
        self.assertNotIn(self.area.pk, ids)


class WorldBuilderAreaManagerTests(WorldBuilderApiBase):
    def _url(self, area=None) -> str:
        return f"/api/world-builder/areas/{(area or self.area).pk}/manager/"

    def test_anonymous_rejected(self) -> None:
        response = self.client.get(self._url())
        self.assertIn(
            response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_non_staff_rejected(self) -> None:
        response = self._get(self._url(), self.player_account)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_area_is_404(self) -> None:
        response = self._get("/api/world-builder/areas/999999/manager/", self.staff_account)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_sees_private_room_with_coords_and_fixture_key(self) -> None:
        response = self._get(self._url(), self.staff_account)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertEqual(data["area"]["id"], self.area.pk)
        self.assertEqual(data["area"]["slug"], "golden-ward")

        rooms_by_id = {row["id"]: row for row in data["rooms"]}
        self.assertEqual(set(rooms_by_id), {self.public_room.pk, self.private_room.pk})

        public_row = rooms_by_id[self.public_room.pk]
        self.assertTrue(public_row["is_public"])
        self.assertTrue(public_row["is_social_hub"])
        self.assertEqual(public_row["fixture_key"], "golden-ward/market-square")
        self.assertEqual(public_row["origin"], GridOrigin.AUTHORED)
        self.assertEqual(public_row["description"], "A bustling market square.")
        self.assertEqual(public_row["grid_x"], 0)
        self.assertEqual(public_row["grid_y"], 0)

        private_row = rooms_by_id[self.private_room.pk]
        self.assertFalse(private_row["is_public"])
        self.assertIsNone(private_row["fixture_key"])
        self.assertEqual(private_row["grid_x"], 1)
        self.assertEqual(private_row["occupant_count"], 1)
        self.assertEqual(public_row["occupant_count"], 0)

    def test_cross_area_exit_has_to_area_id(self) -> None:
        response = self._get(self._url(), self.staff_account)
        exits_by_id = {row["id"]: row for row in response.data["exits"]}

        cross_row = exits_by_id[self.cross_exit.pk]
        self.assertEqual(cross_row["from_room_id"], self.public_room.pk)
        self.assertEqual(cross_row["to_room_id"], self.foreign_room.pk)
        self.assertEqual(cross_row["to_room_name"], "Ashen Gate")
        self.assertEqual(cross_row["to_area_id"], self.other_area.pk)

        intra_row = exits_by_id[self.exit_out.pk]
        self.assertEqual(intra_row["to_area_id"], self.area.pk)

    def test_foreign_area_exit_not_included(self) -> None:
        """Exits whose *location* is outside the requested area are excluded."""
        response = self._get(self._url(), self.staff_account)
        exit_ids = {row["id"] for row in response.data["exits"]}
        self.assertIn(self.cross_exit.pk, exit_ids)  # location IS in this area — included
        self.assertNotIn(self.foreign_exit.pk, exit_ids)  # location is NOT in this area

    def test_manager_payload_includes_clues_triggers_and_anchors(self) -> None:
        """Each room's clue/trigger/anchor placements are nested in its payload row (#2451)."""
        from world.clues.constants import ClueTargetKind
        from world.clues.factories import ClueFactory, ClueTriggerFactory, RoomClueFactory
        from world.magic.factories import PortalAnchorFactory, PortalAnchorKindFactory

        room_profile = self.private_room.room_profile
        clue = ClueFactory(name="Torn Letter", slug="torn-letter", target_kind=ClueTargetKind.CODEX)
        room_clue = RoomClueFactory(room_profile=room_profile, clue=clue, detect_difficulty=5)
        trigger = ClueTriggerFactory(room_profile=room_profile, clue=clue)
        kind = PortalAnchorKindFactory(name="Mirror")
        anchor = PortalAnchorFactory(room_profile=room_profile, kind=kind, name="a mirror")

        response = self._get(self._url(), self.staff_account)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        room_payload = next(r for r in response.data["rooms"] if r["id"] == self.private_room.pk)
        self.assertEqual(
            room_payload["clues"],
            [
                {
                    "id": room_clue.pk,
                    "clue_name": "Torn Letter",
                    "clue_slug": "torn-letter",
                    "detect_difficulty": 5,
                    "fixture_key": room_clue.fixture_key,
                }
            ],
        )
        self.assertEqual(
            room_payload["clue_triggers"],
            [
                {
                    "id": trigger.pk,
                    "clue_name": "Torn Letter",
                    "clue_slug": "torn-letter",
                    "fixture_key": trigger.fixture_key,
                }
            ],
        )
        self.assertEqual(
            room_payload["portal_anchors"],
            [
                {
                    "id": anchor.pk,
                    "kind_name": "Mirror",
                    "name": "a mirror",
                    "fixture_key": anchor.fixture_key,
                }
            ],
        )
        # The other room in this area has none of these placements.
        other_row = next(r for r in response.data["rooms"] if r["id"] == self.public_room.pk)
        self.assertEqual(other_row["clues"], [])
        self.assertEqual(other_row["clue_triggers"], [])
        self.assertEqual(other_row["portal_anchors"], [])
