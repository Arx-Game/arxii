"""E2E journeys for player-postable bulletin boards (#3286).

One journey per board kind — post -> read as the right audience -> denied as
the wrong audience -> moderate — per the spec's test seams. The LOCATION
journey drives the real telnet surface (``CmdBoard``); the ORG journey drives
the shared ``action.run()`` seam directly (org boards have no telnet surface,
per spec Decision 6 — the web OrgPage Board tab is their front door, but both
routes converge on the same Actions this test exercises).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from actions.definitions.boards import PostToBoardAction, RemoveBoardPostAction
from actions.tests.room_test_helpers import character_in_room
from commands.boards import CmdBoard
from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.boards.models import BoardPost
from world.boards.services import visible_posts_for_board
from world.character_sheets.factories import CharacterSheetFactory
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory


def _run(cmd_cls: type, caller: object, args: str = "") -> object:
    """Wire a command instance to ``caller`` (mirrors the covenant E2E helper)."""
    cmd = cmd_cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd_cls.key} {args}".strip()
    caller.msg = MagicMock()
    return cmd


class LocationBoardJourneyTests(TestCase):
    """post -> read as present -> denied as absent -> staff moderates."""

    def setUp(self) -> None:
        self.room_profile = RoomProfileFactory()
        kind = RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.NOTICE_BOARD)
        RoomFeatureInstanceFactory(room_profile=self.room_profile, feature_kind=kind)
        self.poster_sheet, self.poster = character_in_room(self.room_profile)
        self.reader_sheet, self.reader = character_in_room(self.room_profile)

    def test_full_journey(self) -> None:
        # Post as a present character.
        cmd = _run(CmdBoard, self.poster, "post Lost Cat=Answers to Whiskers, seen near the well.")
        cmd.func()
        self.assertEqual(BoardPost.objects.count(), 1)
        post = BoardPost.objects.get()
        self.assertEqual(post.author_persona_id, self.poster_sheet.primary_persona.pk)

        # Read as another present character — the right audience.
        cmd = _run(CmdBoard, self.reader, "read 1")
        cmd.func()
        self.reader.msg.assert_called()
        self.assertIn("Lost Cat", self.reader.msg.call_args[0][0])

        # Denied as the wrong audience: a character standing elsewhere has no
        # board at all — CmdBoard reports the refusal rather than raising past func().
        elsewhere = RoomProfileFactory()
        _, absent_character = character_in_room(elsewhere)
        cmd = _run(CmdBoard, absent_character, "post Sneaky=Should not land.")
        cmd.func()
        absent_character.msg.assert_called_with("There is no board here.")
        self.assertEqual(BoardPost.objects.count(), 1)

        # Moderate: staff removes the post outright (RemoveBoardPostAction, staff bypass).
        staff_sheet = CharacterSheetFactory()
        staff_character = staff_sheet.character
        staff_account = AccountFactory(username="board_staff", is_staff=True)
        staff_character.db_account = staff_account
        staff_character.save()
        result = RemoveBoardPostAction().run(actor=staff_character, post_id=post.pk)
        self.assertTrue(result.success, result.message)
        post.refresh_from_db()
        self.assertTrue(post.is_removed)

        # Removed post no longer surfaces on a read.
        cmd = _run(CmdBoard, self.reader, "")
        cmd.func()
        self.assertIn("no notices", self.reader.msg.call_args[0][0])


class OrgBoardJourneyTests(TestCase):
    """post -> read as member -> denied as non-member -> moderator removes."""

    def setUp(self) -> None:
        self.organization = OrganizationFactory()
        poster_sheet = CharacterSheetFactory()
        self.poster_membership = OrganizationMembershipFactory(
            organization=self.organization, persona=poster_sheet.primary_persona
        )
        self.poster_membership.rank.can_post_to_board = True
        self.poster_membership.rank.save(update_fields=["can_post_to_board"])
        self.poster_character = poster_sheet.character

        reader_sheet = CharacterSheetFactory()
        self.reader_membership = OrganizationMembershipFactory(
            organization=self.organization, persona=reader_sheet.primary_persona
        )

    def test_full_journey(self) -> None:
        # Post as a member with posting rights (lazy board creation via board_id-less
        # org resolution isn't wired for telnet — the web OrgPage flow supplies board_id).
        from world.boards.services import get_or_create_org_board

        board = get_or_create_org_board(self.organization)
        result = PostToBoardAction().run(
            actor=self.poster_character,
            board_id=board.pk,
            title="Muster",
            body="All hands at dusk.",
        )
        self.assertTrue(result.success, result.message)
        post = BoardPost.objects.get()

        # Read as a fellow member — the right audience.
        visible_titles = [p.title for p in visible_posts_for_board(board)]
        self.assertIn("Muster", visible_titles)

        # Denied as the wrong audience: a non-member's post attempt fails.
        outsider_sheet = CharacterSheetFactory()
        denied = PostToBoardAction().run(
            actor=outsider_sheet.character,
            board_id=board.pk,
            title="Intrusion",
            body="Should not land.",
        )
        self.assertFalse(denied.success)
        self.assertEqual(BoardPost.objects.count(), 1)

        # Moderate: leadership (can_moderate_board) removes the post.
        self.poster_membership.rank.can_moderate_board = True
        self.poster_membership.rank.save(update_fields=["can_moderate_board"])
        remove_result = RemoveBoardPostAction().run(actor=self.poster_character, post_id=post.pk)
        self.assertTrue(remove_result.success, remove_result.message)
        post.refresh_from_db()
        self.assertTrue(post.is_removed)
