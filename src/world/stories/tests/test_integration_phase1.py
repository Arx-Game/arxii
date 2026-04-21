"""End-to-end integration test for Stories System Phase 1.

Walks the full 'Crucible: Who Am I?' scenario:
  - Staff creates an active Era.
  - Author builds Story / Chapter / Episodes / Beats / Transitions /
    EpisodeProgressionRequirements / TransitionRequiredOutcomes.
  - Player's character levels up → auto-satisfies the gating beat.
  - GM marks the meeting beat → transition eligibility resolves to ep_2a.
  - resolve_episode fires, advances progress to ep_2a.
  - BeatCompletion + EpisodeResolution audit trail verified.

This is the keystone test for Phase 1: if this passes, the whole backend
foundation is structurally sound.
"""

from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.roster.factories import RosterEntryFactory, RosterFactory
from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    EraStatus,
    StoryScope,
    TransitionMode,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EpisodeProgressionRequirementFactory,
    EraFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
    TransitionRequiredOutcomeFactory,
)
from world.stories.models import BeatCompletion, EpisodeResolution
from world.stories.services.beats import evaluate_auto_beats, record_gm_marked_outcome
from world.stories.services.episodes import resolve_episode
from world.stories.services.transitions import get_eligible_transitions
from world.stories.types import ConnectionType


class FullLoopPhase1IntegrationTest(EvenniaTestCase):
    """End-to-end integration test walking the complete Phase 1 loop."""

    def test_crucible_who_am_i_episode_1_to_2(self):
        # ------------------------------------------------------------------ #
        # Arrange: Era, character, story structure, beats, transitions.       #
        # ------------------------------------------------------------------ #

        # 1. Staff creates an active Era.
        era = EraFactory(status=EraStatus.ACTIVE, season_number=1, name="era_shadows_light")

        # 2. Author creates a CHARACTER-scoped story for this character.
        sheet = CharacterSheetFactory()

        # Wire up a RosterEntry so BeatCompletion.roster_entry is populated.
        roster = RosterFactory()
        roster_entry = RosterEntryFactory(character_sheet=sheet, roster=roster)

        story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=sheet,
            created_in_era=era,
        )
        chapter = ChapterFactory(story=story)

        ep_1 = EpisodeFactory(chapter=chapter, title="Ch1 Ep1: The Mysterious Past")
        ep_2a = EpisodeFactory(chapter=chapter, title="Ch1 Ep2A: The Revelation")
        ep_2b = EpisodeFactory(chapter=chapter, title="Ch1 Ep2B: The Doubt")

        # 3. Author creates beats.
        gating_beat = BeatFactory(
            episode=ep_1,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=2,
            internal_description="Reach level 2",
            player_hint="Continue growing before the next revelation.",
        )
        meeting_beat = BeatFactory(
            episode=ep_1,
            predicate_type=BeatPredicateType.GM_MARKED,
            internal_description="Meeting with the Herald NPC",
            player_hint="A stranger watches you from the edge of the market.",
        )

        # 4. Gating: episode cannot progress until gating_beat == SUCCESS.
        EpisodeProgressionRequirementFactory(
            episode=ep_1, beat=gating_beat, required_outcome=BeatOutcome.SUCCESS
        )

        # 5. Routing: ep_1 → ep_2a when meeting SUCCESS; ep_1 → ep_2b when FAILURE.
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
            transition=t_to_2a, beat=meeting_beat, required_outcome=BeatOutcome.SUCCESS
        )
        TransitionRequiredOutcomeFactory(
            transition=t_to_2b, beat=meeting_beat, required_outcome=BeatOutcome.FAILURE
        )

        # 6. Place the character at ep_1.
        progress = StoryProgressFactory(story=story, character_sheet=sheet, current_episode=ep_1)

        # ------------------------------------------------------------------ #
        # Act 1: Before level-up, auto eval does nothing.                     #
        # ------------------------------------------------------------------ #
        evaluate_auto_beats(progress)
        gating_beat.refresh_from_db()
        self.assertEqual(
            gating_beat.outcome,
            BeatOutcome.UNSATISFIED,
            "gating_beat must remain UNSATISFIED before the character levels up",
        )

        # No transitions eligible yet because progression requirement is unmet.
        self.assertEqual(
            list(get_eligible_transitions(progress)),
            [],
            "No transitions should be eligible while gating_beat is UNSATISFIED",
        )

        # ------------------------------------------------------------------ #
        # Act 2: Level up — auto beat satisfies.                              #
        # ------------------------------------------------------------------ #
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(character=sheet.character, character_class=char_class, level=2)
        evaluate_auto_beats(progress)

        gating_beat.refresh_from_db()
        self.assertEqual(
            gating_beat.outcome,
            BeatOutcome.SUCCESS,
            "gating_beat must flip to SUCCESS once the character reaches level 2",
        )

        # BeatCompletion row created with correct anchors.
        gating_completion = BeatCompletion.objects.get(beat=gating_beat, character_sheet=sheet)
        self.assertEqual(
            gating_completion.era,
            era,
            "BeatCompletion.era must match the active Era",
        )
        self.assertEqual(
            gating_completion.roster_entry,
            roster_entry,
            "BeatCompletion.roster_entry must match the character's RosterEntry",
        )

        # ------------------------------------------------------------------ #
        # Act 3: Progression gate passed, but routing not yet decided.        #
        # ------------------------------------------------------------------ #
        # meeting_beat is still UNSATISFIED → neither t_to_2a nor t_to_2b eligible.
        self.assertEqual(
            list(get_eligible_transitions(progress)),
            [],
            "Transitions should still be ineligible while meeting_beat is UNSATISFIED",
        )

        # ------------------------------------------------------------------ #
        # Act 4: GM marks the meeting beat SUCCESS.                           #
        # ------------------------------------------------------------------ #
        record_gm_marked_outcome(
            progress=progress,
            beat=meeting_beat,
            outcome=BeatOutcome.SUCCESS,
            gm_notes="Crucible handled the Herald with grace.",
        )

        # ------------------------------------------------------------------ #
        # Act 5: Transition to 2A is now eligible (not 2B).                  #
        # ------------------------------------------------------------------ #
        eligible = get_eligible_transitions(progress)
        self.assertEqual(
            eligible,
            [t_to_2a],
            "Only t_to_2a should be eligible after meeting_beat=SUCCESS",
        )

        # ------------------------------------------------------------------ #
        # Act 6: Resolve the episode.                                         #
        # ------------------------------------------------------------------ #
        resolution = resolve_episode(progress=progress)

        # ------------------------------------------------------------------ #
        # Assert: Progress advanced, resolution row correct.                  #
        # ------------------------------------------------------------------ #
        progress.refresh_from_db()
        self.assertEqual(
            progress.current_episode,
            ep_2a,
            "Progress must advance to ep_2a after resolution",
        )
        self.assertEqual(
            resolution.chosen_transition,
            t_to_2a,
            "EpisodeResolution.chosen_transition must be t_to_2a",
        )
        self.assertEqual(
            resolution.era,
            era,
            "EpisodeResolution.era must match the active Era",
        )
        self.assertEqual(
            resolution.character_sheet,
            sheet,
            "EpisodeResolution.character_sheet must match the character's sheet",
        )

        # ------------------------------------------------------------------ #
        # Audit trail: 2 BeatCompletion rows + 1 EpisodeResolution.           #
        # ------------------------------------------------------------------ #
        self.assertEqual(
            BeatCompletion.objects.filter(character_sheet=sheet).count(),
            2,
            "Expected exactly 2 BeatCompletion rows: gating beat + meeting beat",
        )
        self.assertTrue(
            BeatCompletion.objects.filter(
                beat=meeting_beat, character_sheet=sheet, era=era
            ).exists(),
            "A BeatCompletion row for meeting_beat must exist with correct era",
        )
        self.assertEqual(
            EpisodeResolution.objects.filter(character_sheet=sheet).count(),
            1,
            "Expected exactly 1 EpisodeResolution row",
        )
