"""Service-layer tests for boards: permissions, soft-delete, block/mute exclusion (#3286)."""

from django.test import TestCase

from actions.tests.room_test_helpers import character_in_room
from evennia_extensions.factories import RoomProfileFactory
from world.boards.factories import BoardPostFactory, LocationBoardFactory, OrgBoardFactory
from world.boards.models import BoardPost
from world.boards.services import (
    create_board_post,
    edit_board_post,
    exclude_blocked_and_muted_board_authors,
    get_or_create_location_board,
    get_or_create_org_board,
    remove_board_post,
    visible_posts_for_board,
)
from world.boards.types import BoardError
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory


class GetOrCreateBoardTests(TestCase):
    def test_get_or_create_location_board_is_idempotent(self) -> None:
        room_profile = RoomProfileFactory()
        first = get_or_create_location_board(room_profile)
        second = get_or_create_location_board(room_profile)
        self.assertEqual(first.pk, second.pk)

    def test_get_or_create_org_board_is_idempotent(self) -> None:
        organization = OrganizationFactory()
        first = get_or_create_org_board(organization)
        second = get_or_create_org_board(organization)
        self.assertEqual(first.pk, second.pk)


class LocationBoardPostingTests(TestCase):
    def setUp(self) -> None:
        self.room_profile = RoomProfileFactory()
        self.board = LocationBoardFactory(room_profile=self.room_profile)
        self.sheet, self.character = character_in_room(self.room_profile)
        self.persona = self.sheet.primary_persona

    def test_present_character_can_post(self) -> None:
        post = create_board_post(
            board=self.board,
            author_persona=self.persona,
            title="Lost Cat",
            body="Answers to Whiskers.",
            actor_room_profile=self.room_profile,
        )
        self.assertEqual(post.board_id, self.board.pk)
        self.assertEqual(post.author_persona_id, self.persona.pk)

    def test_absent_character_cannot_post(self) -> None:
        elsewhere = RoomProfileFactory()
        with self.assertRaises(BoardError) as ctx:
            create_board_post(
                board=self.board,
                author_persona=self.persona,
                title="Lost Cat",
                body="Answers to Whiskers.",
                actor_room_profile=elsewhere,
            )
        self.assertEqual(ctx.exception.user_message, BoardError.NOT_PRESENT)

    def test_author_can_remove_own_post_while_present(self) -> None:
        post = BoardPostFactory(board=self.board, author_persona=self.persona)
        removed = remove_board_post(
            post=post,
            remover_persona=self.persona,
            actor_room_profile=self.room_profile,
        )
        self.assertTrue(removed.is_removed)
        self.assertEqual(removed.removed_by_persona_id, self.persona.pk)

    def test_author_cannot_remove_own_post_while_absent(self) -> None:
        post = BoardPostFactory(board=self.board, author_persona=self.persona)
        elsewhere = RoomProfileFactory()
        with self.assertRaises(BoardError) as ctx:
            remove_board_post(
                post=post,
                remover_persona=self.persona,
                actor_room_profile=elsewhere,
            )
        self.assertEqual(ctx.exception.user_message, BoardError.NOT_PRESENT)

    def test_staff_can_remove_without_presence(self) -> None:
        post = BoardPostFactory(board=self.board, author_persona=self.persona)
        other_persona = PersonaFactory()
        removed = remove_board_post(
            post=post,
            remover_persona=other_persona,
            actor_room_profile=None,
            is_staff=True,
        )
        self.assertTrue(removed.is_removed)

    def test_non_author_non_staff_cannot_remove(self) -> None:
        post = BoardPostFactory(board=self.board, author_persona=self.persona)
        other_persona = PersonaFactory()
        with self.assertRaises(BoardError) as ctx:
            remove_board_post(
                post=post,
                remover_persona=other_persona,
                actor_room_profile=self.room_profile,
            )
        self.assertEqual(ctx.exception.user_message, BoardError.NOT_AUTHORIZED_TO_REMOVE)

    def test_removing_already_removed_post_raises(self) -> None:
        post = BoardPostFactory(board=self.board, author_persona=self.persona)
        remove_board_post(
            post=post, remover_persona=self.persona, actor_room_profile=self.room_profile
        )
        with self.assertRaises(BoardError) as ctx:
            remove_board_post(
                post=post, remover_persona=self.persona, actor_room_profile=self.room_profile
            )
        self.assertEqual(ctx.exception.user_message, BoardError.ALREADY_REMOVED)

    def test_edit_own_post_does_not_require_presence(self) -> None:
        """LOCATION board editing is author-only — presence is only required for
        post/remove-own (#3286 Decision 3)."""
        post = BoardPostFactory(board=self.board, author_persona=self.persona)
        edited = edit_board_post(
            post=post, editor_persona=self.persona, title="Updated Title", body="New body."
        )
        self.assertEqual(edited.title, "Updated Title")
        self.assertIsNotNone(edited.edited_at)

    def test_edit_by_non_author_raises(self) -> None:
        post = BoardPostFactory(board=self.board, author_persona=self.persona)
        other_persona = PersonaFactory()
        with self.assertRaises(BoardError) as ctx:
            edit_board_post(post=post, editor_persona=other_persona, title="X", body="Y")
        self.assertEqual(ctx.exception.user_message, BoardError.NOT_AUTHOR)


class OrgBoardPostingTests(TestCase):
    def setUp(self) -> None:
        self.organization = OrganizationFactory()
        self.board = OrgBoardFactory(organization=self.organization)

    def test_member_with_can_post_to_board_can_post(self) -> None:
        membership = OrganizationMembershipFactory(organization=self.organization)
        membership.rank.can_post_to_board = True
        membership.rank.save(update_fields=["can_post_to_board"])

        post = create_board_post(
            board=self.board,
            author_persona=membership.persona,
            title="Muster",
            body="All hands at dusk.",
        )
        self.assertEqual(post.board_id, self.board.pk)

    def test_member_without_flag_cannot_post(self) -> None:
        membership = OrganizationMembershipFactory(organization=self.organization)
        membership.rank.can_post_to_board = False
        membership.rank.save(update_fields=["can_post_to_board"])

        with self.assertRaises(BoardError) as ctx:
            create_board_post(
                board=self.board, author_persona=membership.persona, title="Muster", body="Body"
            )
        self.assertEqual(ctx.exception.user_message, BoardError.NOT_AUTHORIZED_TO_POST)

    def test_non_member_cannot_post(self) -> None:
        outsider = PersonaFactory()
        with self.assertRaises(BoardError):
            create_board_post(board=self.board, author_persona=outsider, title="X", body="Y")

    def test_moderator_can_remove_others_post(self) -> None:
        author_membership = OrganizationMembershipFactory(organization=self.organization)
        moderator_membership = OrganizationMembershipFactory(organization=self.organization)
        moderator_membership.rank.can_moderate_board = True
        moderator_membership.rank.save(update_fields=["can_moderate_board"])

        post = BoardPostFactory(board=self.board, author_persona=author_membership.persona)
        removed = remove_board_post(post=post, remover_persona=moderator_membership.persona)
        self.assertTrue(removed.is_removed)

    def test_non_moderator_cannot_remove_others_post(self) -> None:
        author_membership = OrganizationMembershipFactory(organization=self.organization)
        bystander_membership = OrganizationMembershipFactory(organization=self.organization)
        bystander_membership.rank.can_moderate_board = False
        bystander_membership.rank.save(update_fields=["can_moderate_board"])

        post = BoardPostFactory(board=self.board, author_persona=author_membership.persona)
        with self.assertRaises(BoardError) as ctx:
            remove_board_post(post=post, remover_persona=bystander_membership.persona)
        self.assertEqual(ctx.exception.user_message, BoardError.NOT_AUTHORIZED_TO_REMOVE)

    def test_author_can_remove_own_org_post(self) -> None:
        membership = OrganizationMembershipFactory(organization=self.organization)
        post = BoardPostFactory(board=self.board, author_persona=membership.persona)
        removed = remove_board_post(post=post, remover_persona=membership.persona)
        self.assertTrue(removed.is_removed)


class VisiblePostsDisplayCapTests(TestCase):
    def test_display_cap_hides_oldest_but_retains_in_db(self) -> None:
        from datetime import timedelta

        from django.utils import timezone

        board = LocationBoardFactory(max_active_posts=2)
        now = timezone.now()
        first = BoardPostFactory(board=board, title="First")
        second = BoardPostFactory(board=board, title="Second")
        third = BoardPostFactory(board=board, title="Third")
        # auto_now_add ignores an assigned value at create() — explicit .update()
        # afterward gives each post a distinct, ordering-deterministic timestamp.
        BoardPost.objects.filter(pk=first.pk).update(created_at=now - timedelta(minutes=2))
        BoardPost.objects.filter(pk=second.pk).update(created_at=now - timedelta(minutes=1))
        BoardPost.objects.filter(pk=third.pk).update(created_at=now)

        visible = list(visible_posts_for_board(board))
        self.assertEqual(len(visible), 2)
        self.assertEqual({p.title for p in visible}, {"Second", "Third"})
        # Retained in the DB despite falling off the display.
        self.assertEqual(board.posts.count(), 3)

    def test_removed_posts_excluded_from_display(self) -> None:
        board = LocationBoardFactory()
        kept = BoardPostFactory(board=board)
        removed = BoardPostFactory(board=board)
        remove_board_post(post=removed, remover_persona=removed.author_persona, is_staff=True)

        visible_pks = {p.pk for p in visible_posts_for_board(board)}
        self.assertEqual(visible_pks, {kept.pk})


class BlockMuteExclusionTests(TestCase):
    def test_anonymous_viewer_gets_unfiltered_queryset(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        board = LocationBoardFactory()
        BoardPostFactory(board=board)
        queryset = BoardPost.objects.filter(board=board)
        result = exclude_blocked_and_muted_board_authors(queryset, viewer_account=AnonymousUser())
        self.assertEqual(result.count(), queryset.count())

    def test_blocked_author_excluded_from_read(self) -> None:
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )
        from world.scenes.models import Block

        viewer_player = PlayerDataFactory()
        viewer_entry = RosterEntryFactory()
        RosterTenureFactory(player_data=viewer_player, roster_entry=viewer_entry)

        author_entry = RosterEntryFactory()
        author_player = PlayerDataFactory()
        RosterTenureFactory(player_data=author_player, roster_entry=author_entry)
        author_persona = author_entry.character_sheet.primary_persona

        board = LocationBoardFactory()
        post = BoardPostFactory(board=board, author_persona=author_persona)

        Block.objects.create(owner=viewer_player, blocked_player=author_player, account_level=True)

        queryset = BoardPost.objects.filter(pk=post.pk)
        result = exclude_blocked_and_muted_board_authors(
            queryset, viewer_account=viewer_player.account
        )
        self.assertFalse(result.exists())
