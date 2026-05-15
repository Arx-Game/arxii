"""End-to-end pipeline test for the magic-story slice.

Validates: cast a technique with Hallowed Rejection in a celestial-aura room
→ reactive trigger fires → check resolves → condition applied → beat satisfies
→ story progresses → narrative messages publish → achievement granted.

Test data dependencies (seeded by seed_starter_magic_story):
- ConditionTemplate "Hallowed Rejection" (the marker)
- ConditionTemplate "Singed", "Burning", "Tempered Against Light", "Hallowed Burn", "Cast Disrupted"
- TriggerDefinition "Hallowed Rejection — technique cast in celestial-aura room"
- FlowDefinition "Hallowed Rejection reactive flow"
- Room "The Hallowed Threshold (Low)" with 1 Celestial resonance (intensity → difficulty 15)
- Room "The Hallowed Threshold (High)" with 3 Celestial resonances (intensity → difficulty 25)
- Story "The Hallowed Threshold" with Chapter/Episodes/Beats/Transitions/TROs
- Achievements "Hallowed-Hardened", "Touched by Light", "Cast Out by the Light"
- CheckOutcomes "Critical Success", "Success", "Failure", "Critical Failure"
"""

from __future__ import annotations

from unittest.mock import MagicMock

from evennia.utils.test_resources import EvenniaTestCase
from parameterized import parameterized

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
        cls.tempered_template = ConditionTemplate.objects.get(name="Tempered Against Light")
        cls.burning_template = ConditionTemplate.objects.get(name="Burning")
        cls.hallowed_burn_template = ConditionTemplate.objects.get(name="Hallowed Burn")
        cls.cast_disrupted_template = ConditionTemplate.objects.get(name="Cast Disrupted")

        # The low-intensity room has exactly 1 Celestial resonance.
        # compute_intensity_difficulty: base=10 + 1×5 = 15.
        cls.low_room = ObjectDB.objects.filter(
            db_key="The Hallowed Threshold (Low)",
            db_typeclass_path="typeclasses.rooms.Room",
        ).first()

        # The high-intensity room has 3 Celestial resonances.
        # compute_intensity_difficulty: base=10 + 3×5 = 25.
        cls.high_room = ObjectDB.objects.filter(
            db_key="The Hallowed Threshold (High)",
            db_typeclass_path="typeclasses.rooms.Room",
        ).first()

        cls.story = Story.objects.get(title="The Hallowed Threshold")

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

        # Apply the Hallowed Rejection marker.  This auto-installs the reactive
        # TriggerDefinition as a Trigger on the caster (T10 extension).
        # Place the caster in the low room temporarily so apply_condition has a
        # valid location (it fires CONDITION_PRE_APPLY against target's location).
        self.caster.location = self.low_room
        self.caster.save()

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

    def _place_caster_in(self, intensity: str) -> None:
        """Place the caster in the room matching the given intensity tier."""
        room = self.low_room if intensity == "low" else self.high_room
        self.caster.location = room
        self.caster.save()

    # -------------------------------------------------------------------------
    # T0-T7: parametrized across all 8 outcome × intensity combinations
    # -------------------------------------------------------------------------

    @parameterized.expand(
        [
            (
                "low_critical_success",
                "low",
                "Critical Success",
                "Tempered Against Light",
                "Tempered Walk",
                "Hallowed-Hardened",
                True,
                15,
            ),
            (
                "low_success",
                "low",
                "Success",
                "Singed",
                "Marked Path",
                "Touched by Light",
                False,
                15,
            ),
            (
                "low_failure",
                "low",
                "Failure",
                "Burning",
                "Marked Path",
                None,
                False,
                15,
            ),
            (
                "low_critical_failure",
                "low",
                "Critical Failure",
                "Hallowed Burn",
                "Cast Out",
                "Cast Out by the Light",
                True,
                15,
            ),
            (
                "high_critical_success",
                "high",
                "Critical Success",
                "Tempered Against Light",
                "Tempered Walk",
                "Hallowed-Hardened",
                True,
                25,
            ),
            (
                "high_success",
                "high",
                "Success",
                "Singed",
                "Marked Path",
                "Touched by Light",
                False,
                25,
            ),
            (
                "high_failure",
                "high",
                "Failure",
                "Burning",
                "Marked Path",
                None,
                False,
                25,
            ),
            (
                "high_critical_failure",
                "high",
                "Critical Failure",
                "Hallowed Burn",
                "Cast Out",
                "Cast Out by the Light",
                True,
                25,
            ),
        ]
    )
    def test_hallowed_threshold(  # noqa: PLR0913 — parametrized test; one arg per scenario column
        self,
        test_id: str,  # noqa: ARG002 — used in docstring / future diagnostics
        intensity: str,
        outcome_name: str,
        expected_condition: str,
        expected_episode: str,
        expected_achievement: str | None,
        expected_discovery: bool,  # noqa: ARG002 — T17 will use this; T16 uses simplified check
        expected_difficulty: int,
    ) -> None:
        """Cast technique → reactive flow → condition → beat → story → achievement.

        Parametrized across 4 outcomes × 2 intensity tiers = 8 subtests.
        """
        self._place_caster_in(intensity)

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
        # T1: Cast inside force_check_outcome(outcome)
        #
        # The force_check_outcome context manager intercepts the NEXT
        # perform_check call (which happens inside the reactive flow after
        # TECHNIQUE_CAST fires) and returns a synthetic CheckResult.
        # The capture object records check_type + target_difficulty.
        # ------------------------------------------------------------------
        forced_outcome = CheckOutcome.objects.get(name=outcome_name)
        with force_check_outcome(forced_outcome) as capture:
            use_technique(
                character=self.caster,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="resolve_result"),
            )

        # ------------------------------------------------------------------
        # T2: Difficulty assertion
        #
        # Low room:  1 Celestial resonance → base=10 + 1×5 = 15.
        # High room: 3 Celestial resonances → base=10 + 3×5 = 25.
        # ------------------------------------------------------------------
        self.assertEqual(
            capture.target_difficulty,
            expected_difficulty,
            f"Expected difficulty={expected_difficulty} for {intensity} intensity room, "
            f"got {capture.target_difficulty}",
        )

        # ------------------------------------------------------------------
        # T3: Expected reaction condition applied to caster
        #
        # The reactive flow's EVALUATE_EQUALS branch for the outcome fires
        # flow_apply_condition(target=caster, condition_name=<expected_condition>).
        # That calls apply_condition which creates a ConditionInstance.
        #
        # For Critical Failure: also assert "Cast Disrupted" was applied.
        # ------------------------------------------------------------------
        from world.conditions.models import ConditionInstance, ConditionTemplate

        expected_cond_template = ConditionTemplate.objects.get(name=expected_condition)
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.caster,
                condition=expected_cond_template,
            ).exists(),
            f"'{expected_condition}' condition must be applied to caster after '{outcome_name}'",
        )

        if outcome_name == "Critical Failure":
            self.assertTrue(
                ConditionInstance.objects.filter(
                    target=self.caster,
                    condition=self.cast_disrupted_template,
                ).exists(),
                "Cast Disrupted must also be applied to caster on Critical Failure",
            )

        # ------------------------------------------------------------------
        # T4: Expected beat flipped to SUCCESS; others still UNSATISFIED
        #
        # apply_condition internally calls _notify_stories_condition_applied
        # → on_condition_applied → on_character_state_changed
        # → evaluate_auto_beats(progress).
        # ------------------------------------------------------------------
        from world.stories.models import BeatCompletion

        beat_for_outcome = Beat.objects.get(
            episode=self.episode_1,
            required_condition_template=expected_cond_template,
        )
        beat_for_outcome.refresh_from_db()
        self.assertEqual(
            beat_for_outcome.outcome,
            BeatOutcome.SUCCESS,
            f"Beat for '{expected_condition}' must be flipped to SUCCESS after condition applied",
        )
        self.assertTrue(
            BeatCompletion.objects.filter(
                beat=beat_for_outcome,
                character_sheet=self.sheet,
            ).exists(),
            f"BeatCompletion ledger row must exist for beat '{expected_condition}'",
        )

        # All other beats in episode 1 must remain UNSATISFIED.
        for beat in Beat.objects.filter(episode=self.episode_1).exclude(
            required_condition_template=expected_cond_template,
        ):
            beat.refresh_from_db()
            self.assertEqual(
                beat.outcome,
                BeatOutcome.UNSATISFIED,
                f"Beat '{beat}' should still be UNSATISFIED",
            )

        # ------------------------------------------------------------------
        # T5: StoryProgress advances to expected destination episode
        #
        # resolve_episode selects the unique eligible transition (AUTO mode)
        # and advances progress to the appropriate destination.
        # ------------------------------------------------------------------
        from world.stories.models import Episode, EpisodeResolution
        from world.stories.services.episodes import resolve_episode

        resolution = resolve_episode(progress=self.progress)
        self.assertIsNotNone(resolution)

        self.progress.refresh_from_db()
        destination = Episode.objects.get(
            chapter__story=self.story,
            title=expected_episode,
        )
        self.assertEqual(
            self.progress.current_episode,
            destination,
            f"StoryProgress must advance to '{expected_episode}' after episode resolution",
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
            beat=beat_for_outcome,
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
        # T7: Achievement assertions
        #
        # If expected_achievement is not None: CharacterAchievement granted;
        # Discovery row exists (first earner in this fresh DB state).
        # If expected_achievement is None (Failure path): no CharacterAchievement
        # should have been granted.
        # ------------------------------------------------------------------
        from world.achievements.models import Achievement, CharacterAchievement, Discovery

        if expected_achievement is not None:
            achievement = Achievement.objects.get(name=expected_achievement)
            self.assertTrue(
                CharacterAchievement.objects.filter(
                    character_sheet=self.sheet,
                    achievement=achievement,
                ).exists(),
                f"'{expected_achievement}' CharacterAchievement must be granted",
            )
            self.assertTrue(
                Discovery.objects.filter(achievement=achievement).exists(),
                f"Discovery row must exist for first earner of '{expected_achievement}'",
            )
        else:
            self.assertFalse(
                CharacterAchievement.objects.filter(character_sheet=self.sheet).exists(),
                "No CharacterAchievement should be granted on a Failure outcome",
            )
