"""Model-level constraint tests for boards (#3286)."""

from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.boards.factories import BoardPostFactory, LocationBoardFactory, OrgBoardFactory
from world.boards.models import Board
from world.societies.factories import OrganizationFactory


class BoardConstraintTests(TestCase):
    def test_neither_anchor_set_rejected(self) -> None:
        with self.assertRaises(IntegrityError):
            Board.objects.create(name="Orphan Board")

    def test_both_anchors_set_rejected(self) -> None:
        room_profile = RoomProfileFactory()
        organization = OrganizationFactory()
        with self.assertRaises(IntegrityError):
            Board.objects.create(
                name="Double Anchor",
                room_profile=room_profile,
                organization=organization,
            )

    def test_one_board_per_room(self) -> None:
        room_profile = RoomProfileFactory()
        LocationBoardFactory(room_profile=room_profile)
        with self.assertRaises(IntegrityError):
            Board.objects.create(name="Second Board", room_profile=room_profile)

    def test_one_board_per_org(self) -> None:
        organization = OrganizationFactory()
        OrgBoardFactory(organization=organization)
        with self.assertRaises(IntegrityError):
            Board.objects.create(name="Second Org Board", organization=organization)

    def test_is_location_board_and_is_org_board(self) -> None:
        location_board = LocationBoardFactory()
        org_board = OrgBoardFactory()
        self.assertTrue(location_board.is_location_board)
        self.assertFalse(location_board.is_org_board)
        self.assertTrue(org_board.is_org_board)
        self.assertFalse(org_board.is_location_board)


class BoardPostModelTests(TestCase):
    def test_is_removed_reflects_removed_at(self) -> None:
        post = BoardPostFactory()
        self.assertFalse(post.is_removed)
        post.removed_at = post.created_at
        self.assertTrue(post.is_removed)

    def test_active_queryset_excludes_removed(self) -> None:
        board = LocationBoardFactory()
        kept = BoardPostFactory(board=board)
        removed = BoardPostFactory(board=board)
        removed.removed_at = removed.created_at
        removed.save(update_fields=["removed_at"])

        active_pks = set(board.posts.active().values_list("pk", flat=True))
        self.assertIn(kept.pk, active_pks)
        self.assertNotIn(removed.pk, active_pks)
