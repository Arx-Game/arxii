"""End-to-end pipeline test for the magic-story slice.

Validates: cast a technique with Hallowed Rejection in a celestial-aura room
→ reactive trigger fires → check resolves → condition applied → beat satisfies
→ story progresses → narrative messages publish → achievement granted.

Test data dependencies (seeded by seed_starter_magic_story):
- ConditionTemplate "Hallowed Rejection" (the marker)
- ConditionTemplate "Singed" (Success outcome reaction)
- TriggerDefinition "Hallowed Rejection — technique cast in celestial-aura room"
- FlowDefinition "Hallowed Rejection reactive flow"
- Room "The Hallowed Threshold (Low)" with 1 Celestial resonance (intensity → difficulty 15)
- Story "The Hallowed Threshold" with Chapter/Episodes/Beats/Transitions/TROs
- Achievement "Touched by Light" for the Singed outcome
- CheckOutcome "Success"
"""

from __future__ import annotations

from unittest.mock import MagicMock

from evennia.utils.test_resources import EvenniaTestCase

from integration_tests.game_content.magic import seed_starter_magic_story
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.services import apply_condition
from world.magic.factories import CharacterAnimaFactory, TechniqueFactory
from world.magic.services.techniques import use_technique
from world.traits.models import CheckOutcome


class MagicStoryPipelineTests(EvenniaTestCase):
    """Full pipeline: cast technique → reactive flow → condition → beat → story → achievement."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        seed_starter_magic_story()

        from evennia.objects.models import ObjectDB

        from world.conditions.models import ConditionTemplate
        from world.stories.models import Story

        cls.hallowed_rejection = ConditionTemplate.objects.get(name="Hallowed Rejection")
        cls.singed_template = ConditionTemplate.objects.get(name="Singed")

        # The low-intensity room has exactly 1 Celestial resonance.
        # compute_intensity_difficulty: base=10 + 1×5 = 15.
        cls.low_room = ObjectDB.objects.filter(
            db_key="The Hallowed Threshold (Low)",
            db_typeclass_path="typeclasses.rooms.Room",
        ).first()

        cls.story = Story.objects.get(title="The Hallowed Threshold")

        # CheckOutcome "Success" (seeded by _seed_endure_hallowed_ground_check).
        cls.success_outcome = CheckOutcome.objects.get(name="Success")

    def setUp(self) -> None:
        super().setUp()

        # Build an Abyssal-affinity caster.  CharacterSheetFactory creates
        # an ObjectDB character + CharacterSheet + PRIMARY Persona in one shot.
        self.sheet = CharacterSheetFactory()
        self.caster = self.sheet.character  # ObjectDB

        # CharacterAnima is required by use_technique (anima cost deduction).
        self.anima = CharacterAnimaFactory(character=self.caster, current=20, maximum=20)

        # Seeded Technique — low intensity so no soulfray accrual.
        # intensity=1, control=1, anima_cost=1 keeps the cast clean.
        self.technique = TechniqueFactory(intensity=1, control=1, anima_cost=1)

        # Place caster in the low-intensity room BEFORE applying the marker.
        # The CONDITION_PRE_APPLY event fires against the target's location;
        # having a valid room avoids None-location errors in apply_condition.
        self.caster.location = self.low_room
        self.caster.save()

        # Apply the Hallowed Rejection marker.  This auto-installs the reactive
        # TriggerDefinition as a Trigger on the caster (T10 extension).
        result = apply_condition(
            target=self.caster,
            condition=self.hallowed_rejection,
        )
        self.assertTrue(
            result.success,
            f"Hallowed Rejection must apply cleanly; got: {result.message}",
        )

        # Create StoryProgress pointing at Episode 1.
        # StoryProgress.clean() allows character_sheet mismatch when
        # story.character_sheet_id is None (the seeded story is a template).
        from world.stories.models import Episode, StoryProgress

        episode_1 = Episode.objects.get(
            chapter__story=self.story,
            title="Stepping Into Light",
        )
        self.episode_1 = episode_1
        self.progress, _ = StoryProgress.objects.get_or_create(
            story=self.story,
            character_sheet=self.sheet,
            defaults={"current_episode": episode_1},
        )

    # -------------------------------------------------------------------------
    # T0-T7: low_success subtest
    # -------------------------------------------------------------------------

    def test_low_success(self) -> None:
        """Cast technique in low celestial room → Success → Singed → story advances."""

        # ------------------------------------------------------------------
        # T0: Pre-state assertions
        # ------------------------------------------------------------------
        from flows.models.triggers import Trigger
        from world.achievements.models import CharacterAchievement
        from world.stories.constants import BeatOutcome
        from world.stories.models import Beat

        # Hallowed Rejection marker should have installed exactly 1 reactive Trigger.
        self.assertEqual(
            Trigger.objects.filter(obj=self.caster).count(),
            1,
            "Hallowed Rejection should have auto-installed exactly 1 reactive Trigger",
        )

        # All beats in Episode 1 should be UNSATISFIED before the cast.
        for beat in Beat.objects.filter(episode=self.episode_1):
            self.assertEqual(
                beat.outcome,
                BeatOutcome.UNSATISFIED,
                f"Beat '{beat}' should be UNSATISFIED before cast",
            )

        # No CharacterAchievements yet.
        self.assertFalse(
            CharacterAchievement.objects.filter(character_sheet=self.sheet).exists(),
            "No achievements should exist before cast",
        )

        # StoryProgress should point at Episode 1.
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.current_episode, self.episode_1)

        # ------------------------------------------------------------------
        # T1: Cast inside force_check_outcome(success)
        #
        # The force_check_outcome context manager intercepts the NEXT
        # perform_check call (which happens inside the reactive flow after
        # TECHNIQUE_CAST fires) and returns a synthetic Success CheckResult.
        # The capture object records check_type + target_difficulty.
        # ------------------------------------------------------------------
        with force_check_outcome(self.success_outcome) as capture:
            use_technique(
                character=self.caster,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="resolve_result"),
            )

        # ------------------------------------------------------------------
        # T2: Difficulty assertion
        #
        # The low room has 1 Celestial resonance.
        # compute_intensity_difficulty(base=10, per_resonance_modifier=5, count=1) = 15.
        # ------------------------------------------------------------------
        self.assertEqual(
            capture.target_difficulty,
            15,
            f"Expected difficulty=15 (10 base + 1×5 Celestial resonance), "
            f"got {capture.target_difficulty}",
        )

        # ------------------------------------------------------------------
        # T3: Singed condition applied to caster
        #
        # The reactive flow's EVALUATE_EQUALS branch for "Success" fires
        # flow_apply_condition(target=caster, condition_name="Singed").
        # That calls apply_condition which creates a ConditionInstance.
        # ------------------------------------------------------------------
        from world.conditions.models import ConditionInstance

        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.caster,
                condition=self.singed_template,
            ).exists(),
            "Singed condition must be applied to caster after Success outcome",
        )

        # ------------------------------------------------------------------
        # T4: Beat-Singed flipped to SUCCESS; others still UNSATISFIED
        #
        # apply_condition internally calls _notify_stories_condition_applied
        # → on_condition_applied → on_character_state_changed
        # → evaluate_auto_beats(progress).  CONDITION_HELD "Singed" is now met.
        # ------------------------------------------------------------------
        from world.stories.models import BeatCompletion

        beat_singed = Beat.objects.get(
            episode=self.episode_1,
            required_condition_template=self.singed_template,
        )
        beat_singed.refresh_from_db()
        self.assertEqual(
            beat_singed.outcome,
            BeatOutcome.SUCCESS,
            "Beat-Singed must be flipped to SUCCESS after Singed is applied",
        )
        self.assertTrue(
            BeatCompletion.objects.filter(
                beat=beat_singed,
                character_sheet=self.sheet,
            ).exists(),
            "BeatCompletion ledger row must exist for Beat-Singed",
        )

        # The other three beats must remain UNSATISFIED.
        for beat in Beat.objects.filter(episode=self.episode_1).exclude(
            required_condition_template=self.singed_template,
        ):
            beat.refresh_from_db()
            self.assertEqual(
                beat.outcome,
                BeatOutcome.UNSATISFIED,
                f"Beat '{beat}' should still be UNSATISFIED",
            )

        # ------------------------------------------------------------------
        # T5: StoryProgress advances to "Marked Path" after resolve_episode
        #
        # The Singed beat success satisfies Transition 3 (Beat-Singed SUCCESS
        # → Marked Path).  resolve_episode selects the unique eligible
        # transition (AUTO mode, single eligible) and advances progress.
        # ------------------------------------------------------------------
        from world.stories.models import Episode, EpisodeResolution
        from world.stories.services.episodes import resolve_episode

        resolution = resolve_episode(progress=self.progress)
        self.assertIsNotNone(resolution)

        self.progress.refresh_from_db()
        marked_path = Episode.objects.get(
            chapter__story=self.story,
            title="Marked Path",
        )
        self.assertEqual(
            self.progress.current_episode,
            marked_path,
            "StoryProgress must advance to 'Marked Path' after episode resolution",
        )

        self.assertTrue(
            EpisodeResolution.objects.filter(
                episode=self.episode_1,
                character_sheet=self.sheet,
            ).exists(),
            "EpisodeResolution ledger row must exist for Episode 1",
        )

        # ------------------------------------------------------------------
        # T6: NarrativeMessage rows for beat completion and episode resolution
        #
        # notify_beat_completion and notify_episode_resolution both create
        # NarrativeMessage rows with related_beat_completion /
        # related_episode_resolution FKs.
        # ------------------------------------------------------------------
        from world.narrative.models import NarrativeMessage

        beat_completion = BeatCompletion.objects.get(
            beat=beat_singed,
            character_sheet=self.sheet,
        )
        beat_msgs = NarrativeMessage.objects.filter(
            related_beat_completion=beat_completion,
        )
        self.assertTrue(
            beat_msgs.exists(),
            "NarrativeMessage rows must exist for the beat completion",
        )

        episode_resolution = EpisodeResolution.objects.get(
            episode=self.episode_1,
            character_sheet=self.sheet,
        )
        episode_msgs = NarrativeMessage.objects.filter(
            related_episode_resolution=episode_resolution,
        )
        self.assertTrue(
            episode_msgs.exists(),
            "NarrativeMessage rows must exist for the episode resolution",
        )

        # ------------------------------------------------------------------
        # T7: CharacterAchievement "Touched by Light" granted; Discovery exists
        #
        # _install_reactive_side_effects increments the stat for "Singed Gained"
        # via ConditionStatRule.  sheet.stats.increment() checks AchievementRequirement
        # thresholds and grants the Achievement when threshold met (≥1).
        # First earner also creates a Discovery row (one-per-achievement).
        # ------------------------------------------------------------------
        from world.achievements.models import (
            Achievement,
            CharacterAchievement,
            Discovery,
        )

        touched = Achievement.objects.get(name="Touched by Light")
        self.assertTrue(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet,
                achievement=touched,
            ).exists(),
            "'Touched by Light' CharacterAchievement must be granted after Singed",
        )
        self.assertTrue(
            Discovery.objects.filter(achievement=touched).exists(),
            "Discovery row must exist for first earner of 'Touched by Light'",
        )
