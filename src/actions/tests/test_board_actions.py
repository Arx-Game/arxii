"""Tests for board Actions (#3286): PostToBoardAction/EditBoardPostAction/RemoveBoardPostAction."""

from django.test import TestCase

from actions.definitions.boards import (
    EditBoardPostAction,
    PostToBoardAction,
    RemoveBoardPostAction,
)
from actions.tests.room_test_helpers import character_in_room
from evennia_extensions.factories import RoomProfileFactory
from world.boards.factories import BoardPostFactory, LocationBoardFactory, OrgBoardFactory
from world.boards.models import BoardPost
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory


class PostToBoardActionLocationTests(TestCase):
    def setUp(self) -> None:
        self.room_profile = RoomProfileFactory()
        kind = RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.NOTICE_BOARD)
        RoomFeatureInstanceFactory(room_profile=self.room_profile, feature_kind=kind)
        self.sheet, self.character = character_in_room(self.room_profile)

    def test_post_lazily_creates_board_and_succeeds(self) -> None:
        self.assertFalse(BoardPost.objects.exists())
        result = PostToBoardAction().run(
            actor=self.character, title="Lost Cat", body="Answers to Whiskers."
        )
        self.assertTrue(result.success, result.message)
        post = BoardPost.objects.get()
        self.assertEqual(post.title, "Lost Cat")
        self.assertEqual(post.author_persona_id, self.sheet.primary_persona.pk)

    def test_post_with_no_board_in_room_fails(self) -> None:
        other_room = RoomProfileFactory()
        _sheet, character = character_in_room(other_room)
        result = PostToBoardAction().run(actor=character, title="X", body="Y")
        self.assertFalse(result.success)

    def test_post_missing_title_or_body_fails(self) -> None:
        result = PostToBoardAction().run(actor=self.character, title="", body="Body")
        self.assertFalse(result.success)


class PostToBoardActionOrgTests(TestCase):
    def test_org_member_with_flag_can_post_via_board_id(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory

        organization = OrganizationFactory()
        board = OrgBoardFactory(organization=organization)
        sheet = CharacterSheetFactory()
        # active_persona_for_sheet resolves the sheet's PRIMARY persona by
        # default, so the membership is minted against that same persona —
        # otherwise the actor's active face and the org membership wouldn't match.
        membership = OrganizationMembershipFactory(
            organization=organization, persona=sheet.primary_persona
        )
        membership.rank.can_post_to_board = True
        membership.rank.save(update_fields=["can_post_to_board"])

        result = PostToBoardAction().run(
            actor=sheet.character,
            board_id=board.pk,
            title="Muster",
            body="At dusk.",
        )
        self.assertTrue(result.success, result.message)

    def test_org_non_member_cannot_post(self) -> None:
        organization = OrganizationFactory()
        board = OrgBoardFactory(organization=organization)
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()

        result = PostToBoardAction().run(
            actor=sheet.character, board_id=board.pk, title="Muster", body="At dusk."
        )
        self.assertFalse(result.success)


class EditBoardPostActionTests(TestCase):
    def test_author_can_edit_own_post(self) -> None:
        room_profile = RoomProfileFactory()
        board = LocationBoardFactory(room_profile=room_profile)
        sheet, character = character_in_room(room_profile)
        post = BoardPostFactory(board=board, author_persona=sheet.primary_persona)

        result = EditBoardPostAction().run(
            actor=character, post_id=post.pk, title="New Title", body="New body."
        )
        self.assertTrue(result.success, result.message)
        post.refresh_from_db()
        self.assertEqual(post.title, "New Title")

    def test_non_author_cannot_edit(self) -> None:
        board = LocationBoardFactory()
        post = BoardPostFactory(board=board)
        room_profile = RoomProfileFactory()
        _, character = character_in_room(room_profile)

        result = EditBoardPostAction().run(
            actor=character, post_id=post.pk, title="New Title", body="New body."
        )
        self.assertFalse(result.success)


class RemoveBoardPostActionTests(TestCase):
    def test_author_present_can_remove_own_location_post(self) -> None:
        room_profile = RoomProfileFactory()
        board = LocationBoardFactory(room_profile=room_profile)
        sheet, character = character_in_room(room_profile)
        post = BoardPostFactory(board=board, author_persona=sheet.primary_persona)

        result = RemoveBoardPostAction().run(actor=character, post_id=post.pk)
        self.assertTrue(result.success, result.message)
        post.refresh_from_db()
        self.assertTrue(post.is_removed)

    def test_non_author_non_staff_cannot_remove(self) -> None:
        board = LocationBoardFactory()
        post = BoardPostFactory(board=board)
        room_profile = RoomProfileFactory()
        _, character = character_in_room(room_profile)

        result = RemoveBoardPostAction().run(actor=character, post_id=post.pk)
        self.assertFalse(result.success)
