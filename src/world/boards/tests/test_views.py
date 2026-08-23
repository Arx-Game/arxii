"""API tests for the boards read endpoints (#3286).

LOCATION boards are visible to everyone; ORG boards are gated on active
membership (mirrors ``world.tasking.tests.test_views``' pattern).
"""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import RoomProfileFactory
from world.boards.factories import BoardPostFactory, LocationBoardFactory, OrgBoardFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory


class BoardApiTestBase(EvenniaTestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.entry = RosterEntryFactory(character_sheet=self.sheet)
        self.tenure = RosterTenureFactory(roster_entry=self.entry, player_number=1)
        self.account = self.tenure.player_data.account
        self.persona = self.sheet.primary_persona
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)


class LocationBoardReadTests(BoardApiTestBase):
    def test_location_board_visible_to_non_member(self) -> None:
        board = LocationBoardFactory()
        response = self.client.get("/api/boards/boards/")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data["results"]]
        self.assertIn(board.pk, ids)

    def test_location_board_posts_visible_to_anyone(self) -> None:
        room_profile = RoomProfileFactory()
        board = LocationBoardFactory(room_profile=room_profile)
        post = BoardPostFactory(board=board)
        response = self.client.get(f"/api/boards/posts/?board={board.pk}")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data["results"]]
        self.assertIn(post.pk, ids)


class OrgBoardReadGatingTests(BoardApiTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.organization = OrganizationFactory()
        self.board = OrgBoardFactory(organization=self.organization)

    def test_non_member_does_not_see_org_board(self) -> None:
        response = self.client.get("/api/boards/boards/")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data["results"]]
        self.assertNotIn(self.board.pk, ids)

    def test_non_member_sees_no_posts_on_org_board(self) -> None:
        BoardPostFactory(board=self.board)
        response = self.client.get(f"/api/boards/posts/?board={self.board.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_member_sees_org_board_and_its_posts(self) -> None:
        OrganizationMembershipFactory(organization=self.organization, persona=self.persona)
        post = BoardPostFactory(board=self.board)

        board_response = self.client.get("/api/boards/boards/")
        board_ids = [row["id"] for row in board_response.data["results"]]
        self.assertIn(self.board.pk, board_ids)

        post_response = self.client.get(f"/api/boards/posts/?board={self.board.pk}")
        post_ids = [row["id"] for row in post_response.data["results"]]
        self.assertIn(post.pk, post_ids)
