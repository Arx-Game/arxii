"""End-to-end integration test for Stories System Phase 2.

Walks a comprehensive Phase 2 scenario:
  - Lead GM (GMProfile) running a GMTable; two player characters as members.
  - A GROUP-scope Story on the Lead GM's primary_table.
  - One chapter, three episodes (ep_1, ep_2a, ep_2b).
  - Beats on ep_1 covering all five new Phase 2 predicate types:
      * mission_beat    — GM_MARKED ("Raid the supply caravan")
      * aggregate_beat  — AGGREGATE_THRESHOLD, required_points=100
      * achievement_beat — ACHIEVEMENT_HELD ("Commander" achievement)
      * condition_beat  — CONDITION_HELD ("Scarred" condition)
      * codex_beat      — CODEX_ENTRY_UNLOCKED ("Shadow Pact" entry)
  - Routing: to_2a fires when mission_beat=SUCCESS; to_2b when FAILURE.
  - Progression gate: aggregate + achievement + condition + codex must all =SUCCESS.
  - Step-by-step assertions covering the full Phase 2 feature surface.

Additional scenarios:
  - Step 10: AGM claim flow on ep_2a.
  - Step 11: Deadline expiry on ep_2a.
  - Step 12: Cross-story STORY_AT_MILESTONE from a CHARACTER-scope story
             referencing the GROUP story at CHAPTER_REACHED milestone.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from evennia.utils.test_resources import EvenniaTestCase

from world.achievements.factories import AchievementFactory, CharacterAchievementFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.codex.factories import CharacterCodexKnowledgeFactory, CodexEntryFactory
from world.codex.models import CharacterCodexKnowledge
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.gm.factories import GMProfileFactory, GMTableFactory, GMTableMembershipFactory
from world.roster.factories import RosterEntryFactory, RosterFactory
from world.scenes.factories import PersonaFactory
from world.stories.constants import (
    AssistantClaimStatus,
    BeatOutcome,
    BeatPredicateType,
    EraStatus,
    StoryMilestoneType,
    StoryScope,
    TransitionMode,
)
from world.stories.exceptions import ProgressionRequirementNotMetError
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EpisodeProgressionRequirementFactory,
    EraFactory,
    GroupStoryProgressFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
    TransitionRequiredOutcomeFactory,
)
from world.stories.models import (
    BeatCompletion,
    EpisodeResolution,
    SessionRequest,
)
from world.stories.services.assistant_gm import (
    approve_claim,
    complete_claim,
    request_claim,
)
from world.stories.services.beats import (
    evaluate_auto_beats,
    expire_overdue_beats,
    record_aggregate_contribution,
    record_gm_marked_outcome,
)
from world.stories.services.episodes import resolve_episode
from world.stories.services.transitions import get_eligible_transitions
from world.stories.types import ConnectionType


class Phase2FullLoopIntegrationTest(EvenniaTestCase):
    """Keystone integration test walking the full Phase 2 feature surface."""

    def test_phase2_full_loop(self) -> None:  # noqa: PLR0915 — keystone integration test; single method intentional
        # ------------------------------------------------------------------ #
        # Arrange: Era, GM infrastructure, characters, GROUP story structure. #
        # ------------------------------------------------------------------ #

        # Active era — every BeatCompletion/EpisodeResolution reads this.
        era = EraFactory(status=EraStatus.ACTIVE, season_number=2, name="era_second_dawn")

        # Lead GM: one GMProfile, one GMTable.
        lead_gm = GMProfileFactory()
        table = GMTableFactory(gm=lead_gm)

        # Two player characters, each with a CharacterSheet and RosterEntry.
        roster = RosterFactory()
        sheet1 = CharacterSheetFactory()
        sheet2 = CharacterSheetFactory()
        roster_entry1 = RosterEntryFactory(character_sheet=sheet1, roster=roster)
        RosterEntryFactory(character_sheet=sheet2, roster=roster)  # needed for codex FK walk

        # Add both characters to the GM table via Persona membership.
        persona1 = PersonaFactory(character_sheet=sheet1)
        persona2 = PersonaFactory(character_sheet=sheet2)
        GMTableMembershipFactory(table=table, persona=persona1)
        GMTableMembershipFactory(table=table, persona=persona2)

        # GROUP-scope story anchored to this table.
        story = StoryFactory(
            scope=StoryScope.GROUP,
            character_sheet=None,
            created_in_era=era,
            primary_table=table,
        )
        chapter = ChapterFactory(story=story)

        ep_1 = EpisodeFactory(chapter=chapter, title="Ep 1: Raid the Caravan")
        ep_2a = EpisodeFactory(chapter=chapter, title="Ep 2A: Victorious March")
        ep_2b = EpisodeFactory(chapter=chapter, title="Ep 2B: Tactical Retreat")

        # ----- Beats on ep_1 ----- #
        mission_beat = BeatFactory(
            episode=ep_1,
            predicate_type=BeatPredicateType.GM_MARKED,
            internal_description="Raid the supply caravan",
            player_hint="The caravan approaches at nightfall.",
        )

        aggregate_beat = BeatFactory(
            episode=ep_1,
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            required_points=100,
            internal_description="Gather supplies",
            player_hint="The group needs 100 supply points collectively.",
        )

        achievement = AchievementFactory(slug="commander", name="Commander")
        achievement_beat = BeatFactory(
            episode=ep_1,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=achievement,
            internal_description="Leader earns Commander achievement",
            player_hint="Prove your leadership in battle.",
        )

        condition_template = ConditionTemplateFactory(name="Scarred")
        condition_beat = BeatFactory(
            episode=ep_1,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=condition_template,
            internal_description="Carrier has 'Scarred' condition",
            player_hint="One among you bears the mark of sacrifice.",
        )

        codex_entry = CodexEntryFactory(name="Shadow Pact")
        codex_beat = BeatFactory(
            episode=ep_1,
            predicate_type=BeatPredicateType.CODEX_ENTRY_UNLOCKED,
            required_codex_entry=codex_entry,
            internal_description="Discover Codex entry 'Shadow Pact'",
            player_hint="Ancient knowledge may guide your path.",
        )

        # All four auto-beats are required for progression.
        EpisodeProgressionRequirementFactory(
            episode=ep_1, beat=aggregate_beat, required_outcome=BeatOutcome.SUCCESS
        )
        EpisodeProgressionRequirementFactory(
            episode=ep_1, beat=achievement_beat, required_outcome=BeatOutcome.SUCCESS
        )
        EpisodeProgressionRequirementFactory(
            episode=ep_1, beat=condition_beat, required_outcome=BeatOutcome.SUCCESS
        )
        EpisodeProgressionRequirementFactory(
            episode=ep_1, beat=codex_beat, required_outcome=BeatOutcome.SUCCESS
        )

        # Routing: mission_beat SUCCESS → 2a; FAILURE → 2b.
        t_to_2a = TransitionFactory(
            source_episode=ep_1,
            target_episode=ep_2a,
            mode=TransitionMode.AUTO,
            connection_type=ConnectionType.THEREFORE,
        )
        t_to_2b = TransitionFactory(
            source_episode=ep_1,
            target_episode=ep_2b,
            mode=TransitionMode.AUTO,
            connection_type=ConnectionType.BUT,
        )
        TransitionRequiredOutcomeFactory(
            transition=t_to_2a, beat=mission_beat, required_outcome=BeatOutcome.SUCCESS
        )
        TransitionRequiredOutcomeFactory(
            transition=t_to_2b, beat=mission_beat, required_outcome=BeatOutcome.FAILURE
        )

        # GroupStoryProgress: group starts at ep_1.
        group_progress = GroupStoryProgressFactory(
            story=story, gm_table=table, current_episode=ep_1
        )

        # ------------------------------------------------------------------ #
        # Step 1: Initial state — all beats UNSATISFIED.                       #
        # get_eligible_transitions raises (progression requirements unmet).   #
        # ------------------------------------------------------------------ #
        with self.assertRaises(
            ProgressionRequirementNotMetError,
            msg="Expected ProgressionRequirementNotMetError before any beats satisfy",
        ):
            get_eligible_transitions(group_progress)

        for beat in [mission_beat, aggregate_beat, achievement_beat, condition_beat, codex_beat]:
            beat.refresh_from_db()
            self.assertEqual(
                beat.outcome,
                BeatOutcome.UNSATISFIED,
                f"{beat.internal_description} should be UNSATISFIED initially",
            )

        # ------------------------------------------------------------------ #
        # Step 2: Aggregate contributions — crosses threshold on 2nd contrib. #
        # ------------------------------------------------------------------ #
        # Player 1 contributes 60 points — below threshold of 100.
        record_aggregate_contribution(
            beat=aggregate_beat,
            character_sheet=sheet1,
            points=60,
            source_note="Raided the northern cache",
        )
        aggregate_beat.refresh_from_db()
        self.assertEqual(
            aggregate_beat.outcome,
            BeatOutcome.UNSATISFIED,
            "aggregate_beat should still be UNSATISFIED after 60/100 points",
        )

        # Player 2 contributes 50 points — total is 110, crossing the 100 threshold.
        record_aggregate_contribution(
            beat=aggregate_beat,
            character_sheet=sheet2,
            points=50,
            source_note="Raided the southern cache",
        )
        aggregate_beat.refresh_from_db()
        self.assertEqual(
            aggregate_beat.outcome,
            BeatOutcome.SUCCESS,
            "aggregate_beat must flip to SUCCESS after total contributions reach 110 (>= 100)",
        )

        # BeatCompletion for GROUP scope: gm_table is set, character_sheet is null.
        agg_completion = BeatCompletion.objects.get(beat=aggregate_beat)
        self.assertIsNone(
            agg_completion.character_sheet,
            "GROUP-scope BeatCompletion must not have character_sheet",
        )
        self.assertEqual(
            agg_completion.gm_table,
            table,
            "GROUP-scope BeatCompletion.gm_table must be the group's GMTable",
        )
        self.assertEqual(
            agg_completion.era,
            era,
            "BeatCompletion.era must match the active era",
        )

        # ------------------------------------------------------------------ #
        # Step 3: Achievement predicate — grant achievement, eval auto beats. #
        # ------------------------------------------------------------------ #
        # Grant the "Commander" achievement to sheet1.
        # Production code: achievement services call CharacterAchievementFactory internally.
        # We use direct model creation here (achievement service API path is equivalent).
        CharacterAchievementFactory(character_sheet=sheet1, achievement=achievement)
        sheet1.invalidate_achievement_cache()

        # Wave 5: GROUP-scope character-state predicates use ANY-member semantics.
        # evaluate_auto_beats iterates active group members and flips SUCCESS on
        # the first member that satisfies the predicate.
        evaluate_auto_beats(group_progress)

        achievement_beat.refresh_from_db()
        self.assertEqual(
            achievement_beat.outcome,
            BeatOutcome.SUCCESS,
            "achievement_beat flips to SUCCESS for GROUP scope when ANY active "
            "member has the achievement (Wave 5 ANY-member semantics).",
        )

        # ------------------------------------------------------------------ #
        # Step 4: Condition predicate — attach condition, ANY-member flip.    #
        # ------------------------------------------------------------------ #
        # Attach a Scarred ConditionInstance to sheet2's character (ObjectDB).
        ConditionInstanceFactory(
            target=sheet2.character,
            condition=condition_template,
            is_suppressed=False,
        )
        sheet2.invalidate_condition_cache()

        evaluate_auto_beats(group_progress)
        condition_beat.refresh_from_db()
        self.assertEqual(
            condition_beat.outcome,
            BeatOutcome.SUCCESS,
            "condition_beat flips to SUCCESS for GROUP scope when ANY active "
            "member has the condition (Wave 5).",
        )

        # ------------------------------------------------------------------ #
        # Step 5: Codex predicate — unlock entry, ANY-member flip.            #
        # ------------------------------------------------------------------ #
        # Unlock the codex entry for sheet1 via CharacterCodexKnowledge.
        CharacterCodexKnowledgeFactory(
            roster_entry=roster_entry1,
            entry=codex_entry,
            status=CharacterCodexKnowledge.Status.KNOWN,
        )

        evaluate_auto_beats(group_progress)
        codex_beat.refresh_from_db()
        self.assertEqual(
            codex_beat.outcome,
            BeatOutcome.SUCCESS,
            "codex_beat flips to SUCCESS for GROUP scope when ANY active "
            "member has the codex entry unlocked (Wave 5).",
        )

        # ------------------------------------------------------------------ #
        # Step 6: Parallel check — CHARACTER-scope auto-evaluation works too. #
        # Confirms the per-sheet predicate helpers are the same code path     #
        # the Wave 5 ANY-member dispatcher reuses under the hood.              #
        # ------------------------------------------------------------------ #
        char_story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=sheet1,
            created_in_era=era,
        )
        char_chapter = ChapterFactory(story=char_story)
        char_ep = EpisodeFactory(chapter=char_chapter)

        char_achievement_beat = BeatFactory(
            episode=char_ep,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=achievement,
        )
        char_codex_beat = BeatFactory(
            episode=char_ep,
            predicate_type=BeatPredicateType.CODEX_ENTRY_UNLOCKED,
            required_codex_entry=codex_entry,
        )

        char_progress = StoryProgressFactory(
            story=char_story, character_sheet=sheet1, current_episode=char_ep
        )

        # evaluate_auto_beats for CHARACTER scope detects achievement and codex.
        evaluate_auto_beats(char_progress)

        char_achievement_beat.refresh_from_db()
        self.assertEqual(
            char_achievement_beat.outcome,
            BeatOutcome.SUCCESS,
            "achievement_beat must flip to SUCCESS for CHARACTER scope when achievement is held",
        )
        char_codex_beat.refresh_from_db()
        self.assertEqual(
            char_codex_beat.outcome,
            BeatOutcome.SUCCESS,
            "codex_beat must flip to SUCCESS for CHARACTER scope when codex entry is KNOWN",
        )

        # Also verify condition_beat for CHARACTER scope using sheet2.
        char_story2 = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=sheet2,
            created_in_era=era,
        )
        char_chapter2 = ChapterFactory(story=char_story2)
        char_ep2 = EpisodeFactory(chapter=char_chapter2)
        char_condition_beat = BeatFactory(
            episode=char_ep2,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=condition_template,
        )
        char_progress2 = StoryProgressFactory(
            story=char_story2, character_sheet=sheet2, current_episode=char_ep2
        )
        evaluate_auto_beats(char_progress2)
        char_condition_beat.refresh_from_db()
        self.assertEqual(
            char_condition_beat.outcome,
            BeatOutcome.SUCCESS,
            "condition_beat must flip to SUCCESS for CHARACTER scope when condition is held",
        )

        # The GROUP-scope achievement/condition/codex beats are already SUCCESS
        # (auto-flipped by Wave 5 ANY-member evaluation above); no manual GM
        # resolution step is needed here.

        # ------------------------------------------------------------------ #
        # Step 7: Eligibility check — all progression requirements met,        #
        # but mission_beat (GM_MARKED) is still UNSATISFIED.                  #
        # get_eligible_transitions returns empty (routing predicate unsatisfied).#
        # ------------------------------------------------------------------ #
        eligible = get_eligible_transitions(group_progress)
        self.assertEqual(
            eligible,
            [],
            "No transitions should be eligible while mission_beat is still UNSATISFIED "
            "(routing predicate not satisfied, but progression gate is now clear).",
        )

        # No SessionRequest should exist yet — maybe_create_session_request
        # requires eligible transitions to be non-empty before creating a request,
        # and the eligible list is empty while mission_beat is UNSATISFIED
        # (routing predicate on both t_to_2a and t_to_2b is unmet).
        self.assertFalse(
            SessionRequest.objects.filter(episode=ep_1).exists(),
            "No SessionRequest should exist while the routing predicate is unsatisfied "
            "(maybe_create_session_request requires eligible transitions).",
        )

        # ------------------------------------------------------------------ #
        # Step 8: GM marks mission_beat SUCCESS — transition to ep_2a.         #
        # record_gm_marked_outcome internally calls maybe_create_session_request.#
        # At this point, t_to_2a becomes eligible AND mission_beat is          #
        # GM_MARKED (still the beat being marked, now SUCCESS), so the        #
        # episode has no remaining UNSATISFIED GM_MARKED beats after marking. #
        # However, t_to_2a is AUTO, so no GM_CHOICE transition exists.        #
        # The episode previously had an UNSATISFIED GM_MARKED beat (mission), #
        # so a SessionRequest would have been created if eligible transitions  #
        # existed. After marking, eligible = [t_to_2a], and if any previously #
        # UNSATISFIED GM_MARKED beat just got resolved, the session was needed.#
        # The service creates the request idempotently on this call.           #
        # ------------------------------------------------------------------ #
        completion = record_gm_marked_outcome(
            progress=group_progress,
            beat=mission_beat,
            outcome=BeatOutcome.SUCCESS,
            gm_notes="The caravan was raided successfully.",
        )
        mission_beat.refresh_from_db()
        self.assertEqual(mission_beat.outcome, BeatOutcome.SUCCESS)

        # BeatCompletion must be GROUP-scoped (gm_table set, character_sheet null).
        self.assertEqual(completion.gm_table, table)
        self.assertIsNone(completion.character_sheet)
        self.assertEqual(completion.era, era)

        # t_to_2a is now eligible; t_to_2b is NOT (mission_beat is SUCCESS, not FAILURE).
        eligible_after_mission = get_eligible_transitions(group_progress)
        self.assertEqual(
            eligible_after_mission,
            [t_to_2a],
            "Only t_to_2a should be eligible after mission_beat=SUCCESS",
        )

        # Verify SessionRequest behaviour: after marking mission_beat SUCCESS, all GM_MARKED
        # beats on ep_1 are resolved, and t_to_2a is AUTO (not GM_CHOICE). So
        # maybe_create_session_request finds needs_gm=False and does NOT create a request.
        # This is correct: the episode can auto-advance without a GM scheduling a session.
        self.assertFalse(
            SessionRequest.objects.filter(episode=ep_1).exists(),
            "No SessionRequest should exist after all beats resolved and no GM involvement "
            "is required (t_to_2a is AUTO, no remaining UNSATISFIED GM_MARKED beats).",
        )

        # Resolve the episode — auto-fires t_to_2a (single AUTO transition).
        resolution = resolve_episode(progress=group_progress)
        group_progress.refresh_from_db()
        self.assertEqual(
            group_progress.current_episode,
            ep_2a,
            "Group progress must advance to ep_2a after resolution",
        )
        self.assertEqual(resolution.chosen_transition, t_to_2a)
        self.assertEqual(resolution.gm_table, table)
        self.assertIsNone(resolution.character_sheet)
        self.assertEqual(resolution.era, era)

        # EpisodeResolution count: exactly 1 (ep_1 → ep_2a).
        self.assertEqual(EpisodeResolution.objects.filter(gm_table=table).count(), 1)

        # ------------------------------------------------------------------ #
        # Step 10: AGM claim flow on ep_2a.                                   #
        # ------------------------------------------------------------------ #
        agm_profile = GMProfileFactory()

        agm_beat = BeatFactory(
            episode=ep_2a,
            predicate_type=BeatPredicateType.GM_MARKED,
            agm_eligible=True,
            internal_description="Assistant GM runs a side scene",
        )

        # AGM requests a claim.
        claim = request_claim(beat=agm_beat, assistant_gm=agm_profile, framing_note="I'll run it.")
        self.assertEqual(claim.status, AssistantClaimStatus.REQUESTED)
        self.assertEqual(claim.assistant_gm, agm_profile)

        # Lead GM approves.
        claim = approve_claim(claim=claim, approver=lead_gm, framing_note="Approved — run it.")
        self.assertEqual(claim.status, AssistantClaimStatus.APPROVED)
        self.assertEqual(claim.approved_by, lead_gm)
        self.assertEqual(claim.framing_note, "Approved — run it.")

        # Lead GM completes the claim after the AGM's session.
        claim = complete_claim(claim=claim, completer=lead_gm)
        self.assertEqual(claim.status, AssistantClaimStatus.COMPLETED)

        # ------------------------------------------------------------------ #
        # Step 11: Deadline expiry on ep_2a.                                  #
        # ------------------------------------------------------------------ #
        past = timezone.now() - timedelta(days=1)
        expiring_beat = BeatFactory(
            episode=ep_2a,
            predicate_type=BeatPredicateType.GM_MARKED,
            deadline=past,
            internal_description="Time-sensitive intel delivery",
        )
        self.assertEqual(expiring_beat.outcome, BeatOutcome.UNSATISFIED)

        expired_count = expire_overdue_beats()
        self.assertGreaterEqual(expired_count, 1, "At least one beat should have expired")

        expiring_beat.refresh_from_db()
        self.assertEqual(
            expiring_beat.outcome,
            BeatOutcome.EXPIRED,
            "expiring_beat must flip to EXPIRED after expire_overdue_beats()",
        )

        # A transition routing on EXPIRED becomes eligible once the beat expires.
        ep_2c = EpisodeFactory(chapter=chapter, title="Ep 2C: Too Late")
        t_to_2c = TransitionFactory(
            source_episode=ep_2a,
            target_episode=ep_2c,
            mode=TransitionMode.AUTO,
            connection_type=ConnectionType.BUT,
        )
        TransitionRequiredOutcomeFactory(
            transition=t_to_2c, beat=expiring_beat, required_outcome=BeatOutcome.EXPIRED
        )

        # get_eligible_transitions for ep_2a (no progression requirements set on ep_2a here)
        # should include t_to_2c since expiring_beat is now EXPIRED.
        group_progress.refresh_from_db()  # Still at ep_2a from step 9 resolution.
        eligible_expired = get_eligible_transitions(group_progress)
        self.assertIn(
            t_to_2c,
            eligible_expired,
            "t_to_2c must be eligible after expiring_beat transitions to EXPIRED",
        )

        # ------------------------------------------------------------------ #
        # Step 12: Cross-story STORY_AT_MILESTONE beat.                        #
        # A CHARACTER-scope story on sheet1 has a beat of type                 #
        # STORY_AT_MILESTONE referencing the GROUP story at CHAPTER_REACHED.   #
        # After ep_1 resolved (advancing to ep_2a, which is still in chapter1),#
        # the milestone check should succeed.                                  #
        # ------------------------------------------------------------------ #
        # Create a CHARACTER-scope story for sheet1 with a cross-story beat.
        milestone_story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=sheet1,
            created_in_era=era,
        )
        milestone_chapter = ChapterFactory(story=milestone_story)
        milestone_ep = EpisodeFactory(chapter=milestone_chapter)
        milestone_beat = BeatFactory(
            episode=milestone_ep,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=story,  # The GROUP story
            referenced_chapter=chapter,  # Chapter 1 of the GROUP story
            referenced_milestone_type=StoryMilestoneType.CHAPTER_REACHED,
            internal_description="GROUP story has reached Chapter 1",
        )
        milestone_progress = StoryProgressFactory(
            story=milestone_story,
            character_sheet=sheet1,
            current_episode=milestone_ep,
        )

        # Group story's current_episode is ep_2a, which is in chapter.
        # chapter.order == 1. CHAPTER_REACHED checks current_chapter.order >=
        # referenced_chapter.order.
        # This should be TRUE since ep_2a is in chapter (same chapter, order >= 1).
        evaluate_auto_beats(milestone_progress)

        milestone_beat.refresh_from_db()
        self.assertEqual(
            milestone_beat.outcome,
            BeatOutcome.SUCCESS,
            "STORY_AT_MILESTONE beat must flip to SUCCESS because the GROUP story's "
            "current episode (ep_2a) is in Chapter 1, satisfying CHAPTER_REACHED.",
        )

        # BeatCompletion for the milestone beat should be CHARACTER-scoped.
        milestone_completion = BeatCompletion.objects.filter(beat=milestone_beat).first()
        self.assertIsNotNone(milestone_completion)
        self.assertEqual(milestone_completion.character_sheet, sheet1)  # type: ignore[union-attr]
        self.assertIsNone(milestone_completion.gm_table)  # type: ignore[union-attr]

        # ------------------------------------------------------------------ #
        # Audit trail summary.                                                 #
        # ------------------------------------------------------------------ #
        # GROUP-scoped completions: aggregate + achievement + condition + codex + mission
        # (5 total for the GROUP table, across ep_1)
        group_completions = BeatCompletion.objects.filter(gm_table=table).count()
        self.assertGreaterEqual(
            group_completions,
            5,
            "Expected at least 5 GROUP-scoped BeatCompletion rows "
            "(aggregate, achievement, condition, codex, mission beats).",
        )

        # CHARACTER-scoped completions for the cross-story milestone beat.
        char_completions = BeatCompletion.objects.filter(character_sheet=sheet1).count()
        self.assertGreaterEqual(
            char_completions,
            1,
            "Expected at least 1 CHARACTER-scoped BeatCompletion row "
            "(milestone beat on sheet1's arc).",
        )
