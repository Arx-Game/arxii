"""End-to-end integration test for Phase 5.

Scenario: walks the full Phase 5 feature surface in one ordered test method,
verifying that every subsystem (era lifecycle, table management, story
assignment / withdrawal / re-offer, beat authoring, session resolution,
narrative messaging, story-OOC / gemit broadcasts, UserStoryMute, table
bulletin board) hangs together correctly.

If this test passes, the Phase 5 feature set is structurally sound end-to-end.
"""

from unittest import mock

from evennia.utils.test_resources import EvenniaTestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory
from world.gm.models import GMTableMembership
from world.gm.services import create_table, join_table, leave_table
from world.narrative.constants import NarrativeCategory
from world.narrative.models import Gemit, UserStoryMute
from world.narrative.services import broadcast_gemit, send_story_ooc_message
from world.scenes.factories import PersonaFactory
from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    EraStatus,
    StoryGMOfferStatus,
    StoryScope,
    TransitionMode,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EraFactory,
    GroupStoryProgressFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
    TransitionRequiredOutcomeFactory,
)
from world.stories.models import (
    Era,
    StoryGMOffer,
    TableBulletinPost,
    TableBulletinReply,
)
from world.stories.services.beats import record_gm_marked_outcome
from world.stories.services.bulletin import create_bulletin_post, reply_to_post
from world.stories.services.episodes import resolve_episode
from world.stories.services.era import advance_era
from world.stories.services.tables import (
    accept_story_offer,
    assign_story_to_table,
    detach_story_from_table,
    offer_story_to_gm,
)


class Phase5EndToEndTests(EvenniaTestCase):
    """Full-system walkthrough of the Phase 5 feature surface."""

    def test_phase5_end_to_end_scenario(self) -> None:  # noqa: PLR0915 — single E2E walkthrough
        # ====================================================================
        # Step 1: Staff creates Era 1 (UPCOMING → ACTIVE via advance_era)
        # ====================================================================
        era1 = EraFactory(
            name="era_1",
            display_name="The First Age",
            season_number=1,
            status=EraStatus.UPCOMING,
        )
        advance_era(next_era=era1)
        era1.refresh_from_db()

        self.assertEqual(era1.status, EraStatus.ACTIVE)
        self.assertIsNotNone(era1.activated_at)

        # ====================================================================
        # Step 2: GM_A creates a table; GM_B creates another table
        # ====================================================================
        gm_a_profile = GMProfileFactory()
        gm_b_profile = GMProfileFactory()

        table_a = create_table(gm=gm_a_profile, name="Table A", description="GM A's table")
        table_b = create_table(gm=gm_b_profile, name="Table B", description="GM B's table")

        self.assertIsNotNone(table_a.pk)
        self.assertIsNotNone(table_b.pk)
        self.assertEqual(table_a.gm, gm_a_profile)
        self.assertEqual(table_b.gm, gm_b_profile)

        # ====================================================================
        # Step 3: Player_1 and Player_2 join GM_A's table (memberships)
        # ====================================================================
        player1_sheet = CharacterSheetFactory()
        player2_sheet = CharacterSheetFactory()
        player1_persona = PersonaFactory(character_sheet=player1_sheet)
        player2_persona = PersonaFactory(character_sheet=player2_sheet)

        membership_p1 = join_table(table=table_a, persona=player1_persona)
        membership_p2 = join_table(table=table_a, persona=player2_persona)

        self.assertIsNotNone(membership_p1.pk)
        self.assertIsNotNone(membership_p2.pk)
        self.assertIsNone(membership_p1.left_at)
        self.assertIsNone(membership_p2.left_at)

        # Verify membership count for table_a.
        active_memberships = GMTableMembership.objects.filter(table=table_a, left_at__isnull=True)
        self.assertEqual(active_memberships.count(), 2)

        # ====================================================================
        # Step 4: GM_A creates a CHARACTER-scope story for Player_1
        #         + assigns it to GM_A's table (assign_story_to_table)
        # ====================================================================
        personal_story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=player1_sheet,
            created_in_era=era1,
            title="Player 1 Personal Arc",
        )
        assign_story_to_table(story=personal_story, table=table_a)
        personal_story.refresh_from_db()

        self.assertEqual(personal_story.primary_table, table_a)
        self.assertEqual(personal_story.created_in_era, era1)

        # ====================================================================
        # Step 5: GM_A creates a GROUP story at the table;
        #         both players added as participants
        # ====================================================================
        group_story = StoryFactory(
            scope=StoryScope.GROUP,
            character_sheet=None,
            created_in_era=era1,
            title="Group Adventure",
        )
        assign_story_to_table(story=group_story, table=table_a)
        group_story.refresh_from_db()

        # Create progress for group story at table_a.
        group_chapter = ChapterFactory(story=group_story)
        group_episode = EpisodeFactory(chapter=group_chapter)
        GroupStoryProgressFactory(
            story=group_story,
            gm_table=table_a,
            current_episode=group_episode,
        )
        self.assertEqual(group_story.primary_table, table_a)

        # ====================================================================
        # Step 6: GM_A authors a beat tree with a transition + required outcome
        # ====================================================================
        char_chapter = ChapterFactory(story=personal_story)
        char_ep1 = EpisodeFactory(chapter=char_chapter)
        char_ep2 = EpisodeFactory(chapter=char_chapter)

        # The beat that the transition guards on.
        guard_beat = BeatFactory(
            episode=char_ep1,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
            player_resolution_text="You face the challenge.",
        )
        # Transition ep1 → ep2 guarded by guard_beat needing SUCCESS.
        transition = TransitionFactory(
            source_episode=char_ep1,
            target_episode=char_ep2,
            mode=TransitionMode.AUTO,
            connection_summary="You press forward.",
        )
        TransitionRequiredOutcomeFactory(
            transition=transition,
            beat=guard_beat,
            required_outcome=BeatOutcome.SUCCESS,
        )

        # Progress record for Player 1's personal story.
        char_progress = StoryProgressFactory(
            story=personal_story,
            character_sheet=player1_sheet,
            current_episode=char_ep1,
        )

        # Verify the required outcome was saved.
        self.assertEqual(transition.required_outcomes.count(), 1)
        self.assertEqual(
            transition.required_outcomes.first().required_outcome,
            BeatOutcome.SUCCESS,
        )

        # ====================================================================
        # Step 7: GM_A runs a session — marks GM_MARKED beat → resolve_episode
        # ====================================================================
        fake_session = mock.Mock()
        player1_char = player1_sheet.character
        with (
            mock.patch.object(player1_char.sessions, "all", return_value=[fake_session]),
            mock.patch.object(player1_char, "msg"),
        ):
            completion = record_gm_marked_outcome(
                progress=char_progress,
                beat=guard_beat,
                outcome=BeatOutcome.SUCCESS,
            )

        guard_beat.refresh_from_db()
        self.assertEqual(guard_beat.outcome, BeatOutcome.SUCCESS)
        self.assertIsNotNone(completion.pk)

        # The guard beat is now SUCCESS → transition is eligible → resolve episode.
        with (
            mock.patch.object(player1_char.sessions, "all", return_value=[fake_session]),
            mock.patch.object(player1_char, "msg"),
        ):
            resolution = resolve_episode(progress=char_progress)

        char_progress.refresh_from_db()
        # Progress should have advanced to char_ep2.
        self.assertEqual(char_progress.current_episode, char_ep2)
        self.assertIsNotNone(resolution.pk)

        # ====================================================================
        # Step 8: Staff broadcasts a Gemit (related_era=Era 1)
        # ====================================================================
        staff_account = AccountFactory()
        gemit = broadcast_gemit(
            body="The First Age begins. Heed the call.",
            sender_account=staff_account,
            related_era=era1,
        )
        self.assertIsNotNone(gemit.pk)
        self.assertEqual(gemit.related_era, era1)
        self.assertEqual(Gemit.objects.filter(related_era=era1).count(), 1)

        # ====================================================================
        # Step 9: Player_1 mutes the GROUP story (UserStoryMute)
        # ====================================================================
        player1_account = AccountFactory()
        mute = UserStoryMute.objects.create(
            account=player1_account,
            story=group_story,
        )
        self.assertIsNotNone(mute.pk)
        self.assertTrue(
            UserStoryMute.objects.filter(account=player1_account, story=group_story).exists()
        )

        # ====================================================================
        # Step 10: GM_A sends story-OOC notice to GROUP participants
        # ====================================================================
        gm_a_account = gm_a_profile.account
        # GROUP story participants = personas at table_a.
        # Both player1_persona and player2_persona are members of table_a.
        with (
            mock.patch.object(player1_char.sessions, "all", return_value=[]),
            mock.patch.object(player1_char, "msg"),
        ):
            ooc_msg = send_story_ooc_message(
                story=group_story,
                sender_account=gm_a_account,
                body="OOC: The session begins at 8pm tonight.",
            )

        self.assertIsNotNone(ooc_msg.pk)
        self.assertEqual(ooc_msg.category, NarrativeCategory.STORY)
        self.assertEqual(ooc_msg.related_story, group_story)
        # There should be delivery rows for both players (membership-based fan-out).
        self.assertEqual(ooc_msg.deliveries.count(), 2)

        # ====================================================================
        # Step 11: Player_1 withdraws personal story from GM_A's table
        # ====================================================================
        detach_story_from_table(story=personal_story)
        personal_story.refresh_from_db()

        self.assertIsNone(personal_story.primary_table)

        # ====================================================================
        # Step 12: Player_1 offers personal story to GM_B
        # ====================================================================
        offered_account = AccountFactory()
        offer = offer_story_to_gm(
            story=personal_story,
            offered_to=gm_b_profile,
            offered_by_account=offered_account,
            message="Would you run my personal arc?",
        )
        self.assertIsNotNone(offer.pk)
        self.assertEqual(offer.status, StoryGMOfferStatus.PENDING)
        self.assertEqual(offer.offered_to, gm_b_profile)
        self.assertTrue(
            StoryGMOffer.objects.filter(
                story=personal_story,
                offered_to=gm_b_profile,
                status=StoryGMOfferStatus.PENDING,
            ).exists()
        )

        # ====================================================================
        # Step 13: GM_B accepts the offer → story is now at GM_B's table
        # ====================================================================
        accepted_offer = accept_story_offer(
            offer=offer,
            response_note="Happy to run this story for you.",
        )
        personal_story.refresh_from_db()

        self.assertEqual(accepted_offer.status, StoryGMOfferStatus.ACCEPTED)
        # accept_story_offer assigns to the GM's first ACTIVE table.
        self.assertEqual(personal_story.primary_table, table_b)

        # ====================================================================
        # Step 14: GM_A creates a table-wide bulletin post (allow_replies=True)
        # ====================================================================
        gm_a_persona = PersonaFactory()
        bulletin_post = create_bulletin_post(
            table=table_a,
            author_persona=gm_a_persona,
            title="Welcome to Table A!",
            body="This is a table-wide announcement for all members.",
            story=None,
            allow_replies=True,
        )
        self.assertIsNotNone(bulletin_post.pk)
        self.assertIsNone(bulletin_post.story)
        self.assertTrue(bulletin_post.allow_replies)
        self.assertEqual(bulletin_post.table, table_a)

        # ====================================================================
        # Step 15: Player_2 replies to the post
        # ====================================================================
        reply = reply_to_post(
            post=bulletin_post,
            author_persona=player2_persona,
            body="Thanks for the update!",
        )
        self.assertIsNotNone(reply.pk)
        self.assertEqual(reply.post, bulletin_post)
        self.assertEqual(TableBulletinReply.objects.filter(post=bulletin_post).count(), 1)

        # ====================================================================
        # Step 16: Story-scoped bulletin post on GROUP story;
        #          Player_1 (still GROUP-participant) sees it
        # ====================================================================
        group_bulletin_post = create_bulletin_post(
            table=table_a,
            author_persona=gm_a_persona,
            title="Group Story Update",
            body="The quest advances — prepare for the confrontation.",
            story=group_story,
            allow_replies=True,
        )
        self.assertIsNotNone(group_bulletin_post.pk)
        self.assertEqual(group_bulletin_post.story, group_story)

        # The post is visible to GROUP story members — verify it's in the DB
        # and associated with the right story.
        self.assertEqual(
            TableBulletinPost.objects.filter(table=table_a, story=group_story).count(),
            1,
        )

        # ====================================================================
        # Step 17: Staff advances Era 1 → Era 2;
        #          broadcasts gemit announcing the new era
        # ====================================================================
        era2 = EraFactory(
            name="era_2",
            display_name="The Second Age",
            season_number=2,
            status=EraStatus.UPCOMING,
        )
        advance_era(next_era=era2)
        era1.refresh_from_db()
        era2.refresh_from_db()

        # Era 1 should now be CONCLUDED; Era 2 should be ACTIVE.
        self.assertEqual(era1.status, EraStatus.CONCLUDED)
        self.assertIsNotNone(era1.concluded_at)
        self.assertEqual(era2.status, EraStatus.ACTIVE)
        self.assertIsNotNone(era2.activated_at)

        # Broadcast a gemit for the new era.
        era2_gemit = broadcast_gemit(
            body="The Second Age dawns. A new chapter begins.",
            sender_account=staff_account,
            related_era=era2,
        )
        self.assertIsNotNone(era2_gemit.pk)
        self.assertEqual(era2_gemit.related_era, era2)
        self.assertEqual(Gemit.objects.count(), 2)

        # ====================================================================
        # Step 18: Player_2 leaves GM_A's table → membership inactive
        #          (no personal stories to detach — player2 had none)
        # ====================================================================
        leave_table(membership=membership_p2)
        membership_p2.refresh_from_db()

        self.assertIsNotNone(membership_p2.left_at)

        # Player_2 had no CHARACTER-scope stories at table_a, so no auto-detach fires.
        # Verify: only player1's membership is still active.
        still_active = GMTableMembership.objects.filter(table=table_a, left_at__isnull=True)
        self.assertEqual(still_active.count(), 1)
        self.assertEqual(still_active.first().persona, player1_persona)

        # ====================================================================
        # Final state assertions
        # ====================================================================
        # Personal story now at GM_B's table.
        personal_story.refresh_from_db()
        self.assertEqual(personal_story.primary_table, table_b)

        # UserStoryMute for Player_1 on GROUP story still exists.
        self.assertTrue(
            UserStoryMute.objects.filter(account=player1_account, story=group_story).exists()
        )

        # Era 2 is ACTIVE.
        active_era = Era.objects.get_active()
        self.assertEqual(active_era, era2)

        # Bulletin posts: 1 table-wide + 1 story-scoped.
        self.assertEqual(TableBulletinPost.objects.filter(table=table_a).count(), 2)

        # Bulletin reply on the table-wide post.
        self.assertEqual(TableBulletinReply.objects.filter(post=bulletin_post).count(), 1)

        # Both gemits in DB.
        self.assertEqual(Gemit.objects.count(), 2)
        self.assertEqual(Gemit.objects.filter(sender_account=staff_account).count(), 2)
