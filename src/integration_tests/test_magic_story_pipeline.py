"""End-to-end pipeline test for the magic-story slice.

Validates: Abyssal-aura caster uses an Abyssal-affinity technique in a
Celestial-cascade room → TECHNIQUE_CAST fires → "Magically Attuned" reactive
trigger runs → flow_evaluate_resonance_environment returns OPPOSED/REJECT →
perform_check at computed backfire difficulty → condition applied → beat
satisfies → story progresses → narrative messages published → achievement
granted.

Cascade math for the Low room (test_low_opposed_success):
  AffinityInteraction(Abyssal→Celestial): OPPOSED, REJECT, severity=1.00
  place_magnitude = effective_value(low_room, Light resonance) = 10
  caster_alignment = aura.abyssal / 100 = 100/100 = 1.0
  raw = 10 * 1.0 * 1.00 * base_coefficient(1.000) = 10.0
  magnitude = round(10.0) = 10
  backfire_difficulty = 30 + round(10 * 0.500) = 35

Test data dependencies (seeded by seed_starter_magic_story):
- ConditionTemplate "Magically Attuned" (ubiquitous baseline; its
  reactive_triggers M2M holds the TECHNIQUE_CAST TriggerDefinition)
- ConditionTemplate "Singed", "Burning", "Tempered Against Light",
  "Hallowed Burn", "Cast Disrupted"
- TriggerDefinition "Resonance Environment — technique cast"
- FlowDefinition "Resonance Environment reactive flow"
- Room "The Hallowed Threshold (Low)" — Celestial cascade magnitude 10
- Room "The Hallowed Threshold (High)" — Celestial cascade magnitude 80
- Room "The Resonant Sanctum (Aligned)" — Abyssal cascade magnitude 60
- AffinityInteraction (Abyssal→Celestial) OPPOSED/REJECT/severity=1.00
- ResonanceEnvironmentConfig (base_coefficient=1.000, caster_power_scalar=0.500,
  backfire_base_difficulty=30, backfire_difficulty_per_magnitude=0.500)
- Story "The Hallowed Threshold" with Chapter/Episodes/Beats/Transitions/TROs
- Achievements "Hallowed-Hardened", "Touched by Light", "Cast Out by the Light"
- CheckOutcomes "Critical Success", "Success", "Failure", "Critical Failure"
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from evennia.utils.test_resources import EvenniaTestCase
from parameterized import parameterized

from integration_tests.game_content.magic import seed_starter_magic_story
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.services import apply_condition
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAuraFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.magic.services.techniques import use_technique
from world.traits.models import CheckOutcome


class MagicStoryPipelineTests(EvenniaTestCase):
    """Full pipeline: Abyssal caster + Abyssal technique + Magically Attuned
    trigger → OPPOSED resonance check → condition → beat → story → achievement."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        seed_starter_magic_story()

        from evennia.objects.models import ObjectDB

        from world.conditions.models import ConditionTemplate
        from world.magic.models.affinity import Resonance
        from world.stories.models import Story

        cls.magically_attuned = ConditionTemplate.objects.get(name="Magically Attuned")
        cls.singed_template = ConditionTemplate.objects.get(name="Singed")
        cls.tempered_template = ConditionTemplate.objects.get(name="Tempered Against Light")
        cls.burning_template = ConditionTemplate.objects.get(name="Burning")
        cls.hallowed_burn_template = ConditionTemplate.objects.get(name="Hallowed Burn")
        cls.cast_disrupted_template = ConditionTemplate.objects.get(name="Cast Disrupted")

        # Low room: Celestial cascade magnitude 10
        # backfire_difficulty = 30 + round(10 * 0.5) = 35
        cls.low_room = ObjectDB.objects.filter(
            db_key="The Hallowed Threshold (Low)",
            db_typeclass_path="typeclasses.rooms.Room",
        ).first()

        # High room: Celestial cascade magnitude 80
        # backfire_difficulty = 30 + round(80 * 0.5) = 70
        cls.high_room = ObjectDB.objects.filter(
            db_key="The Hallowed Threshold (High)",
            db_typeclass_path="typeclasses.rooms.Room",
        ).first()

        # Aligned room: Abyssal cascade magnitude 60 (for ALIGNED boon tests)
        cls.aligned_room = ObjectDB.objects.filter(
            db_key="The Resonant Sanctum (Aligned)",
            db_typeclass_path="typeclasses.rooms.Room",
        ).first()

        cls.story = Story.objects.get(title="The Hallowed Threshold")

        # The seeded Abyssal "Dissolution" resonance — used to wire the technique gift.
        cls.dissolution_resonance = Resonance.objects.get(name="Dissolution")

    def setUp(self) -> None:
        super().setUp()

        # Build an Abyssal-aura caster.  CharacterSheetFactory creates an
        # ObjectDB character + CharacterSheet + PRIMARY Persona in one shot.
        self.sheet = CharacterSheetFactory()
        self.caster = self.sheet.character  # ObjectDB

        # CharacterAura: abyssal=100 so caster_alignment=1.0 against any room.
        # celestial=0, primal=0 (sum must equal 100 per clean()).
        self.aura = CharacterAuraFactory(
            character=self.caster,
            celestial=Decimal("0.00"),
            primal=Decimal("0.00"),
            abyssal=Decimal("100.00"),
        )

        # CharacterAnima is required by use_technique (anima cost deduction).
        self.anima = CharacterAnimaFactory(character=self.caster, current=20, maximum=20)

        # Build an Abyssal-affinity Technique for the caster:
        # create a Gift whose resonances M2M includes "Dissolution" (Abyssal affinity).
        # _working_affinity_cast_time iterates technique.gift.resonances and looks up
        # AffinityInteraction(source=dissolution.affinity, environment=place_affinity).
        # For a Celestial room the seeded row gives OPPOSED/REJECT/severity=1.00.
        gift = GiftFactory(name="Dissolution Arts (pipeline test)")
        gift.resonances.set([self.dissolution_resonance])
        self.technique = TechniqueFactory(
            name="Dissolution Strike (pipeline test)",
            gift=gift,
            intensity=1,
            control=1,
            anima_cost=1,
        )

        # Apply "Magically Attuned" to the caster.
        # This installs the TECHNIQUE_CAST TriggerDefinition as a Trigger on
        # the caster via the T8/T10 ConditionTemplateReactiveHandler path.
        # Place the caster in the low room first so apply_condition has a valid
        # location (it fires CONDITION_PRE_APPLY against target's location).
        self.caster.location = self.low_room
        self.caster.save()

        result = apply_condition(
            target=self.caster,
            condition=self.magically_attuned,
        )
        self.assertTrue(
            result.success,
            f"Magically Attuned must apply cleanly; got: {result.message}",
        )

        # Populate StoryProgress pointing at Episode 1.
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
        room_map = {
            "low": self.low_room,
            "high": self.high_room,
            "aligned": self.aligned_room,
        }
        self.caster.location = room_map[intensity]
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
                35,
            ),
            (
                "low_success",
                "low",
                "Success",
                "Singed",
                "Marked Path",
                "Touched by Light",
                35,
            ),
            (
                "low_failure",
                "low",
                "Failure",
                "Burning",
                "Marked Path",
                None,
                35,
            ),
            (
                "low_critical_failure",
                "low",
                "Critical Failure",
                "Hallowed Burn",
                "Cast Out",
                "Cast Out by the Light",
                35,
            ),
            (
                "high_critical_success",
                "high",
                "Critical Success",
                "Tempered Against Light",
                "Tempered Walk",
                "Hallowed-Hardened",
                70,
            ),
            (
                "high_success",
                "high",
                "Success",
                "Singed",
                "Marked Path",
                "Touched by Light",
                70,
            ),
            (
                "high_failure",
                "high",
                "Failure",
                "Burning",
                "Marked Path",
                None,
                70,
            ),
            (
                "high_critical_failure",
                "high",
                "Critical Failure",
                "Hallowed Burn",
                "Cast Out",
                "Cast Out by the Light",
                70,
            ),
        ]
    )
    def test_opposed_matrix(  # noqa: PLR0913 — parametrized test; one arg per scenario column
        self,
        test_id: str,  # noqa: ARG002 — used by parameterized for method name generation
        intensity: str,
        outcome_name: str,
        expected_condition: str,
        expected_episode: str,
        expected_achievement: str | None,
        expected_difficulty: int,
    ) -> None:
        """Cast technique → resonance check → condition → beat → story → achievement.

        Parametrized across 4 CheckOutcomes × 2 intensity tiers = 8 subtests.

        Low room (celestial mag 10):  backfire_difficulty = 30 + round(10 × 0.5) = 35
        High room (celestial mag 80): backfire_difficulty = 30 + round(80 × 0.5) = 70
        """
        self._place_caster_in(intensity)

        # ------------------------------------------------------------------
        # T0: Pre-state assertions
        # ------------------------------------------------------------------
        from flows.models.triggers import Trigger
        from world.achievements.models import CharacterAchievement
        from world.stories.constants import BeatOutcome
        from world.stories.models import Beat

        # Magically Attuned should have auto-installed exactly 1 reactive Trigger.
        self.assertEqual(
            Trigger.objects.filter(obj=self.caster).count(),
            1,
            "Magically Attuned should have auto-installed exactly 1 reactive Trigger",
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
        # caster_alignment = aura.abyssal / 100 = 100/100 = 1.0
        # AffinityInteraction(Abyssal→Celestial): OPPOSED, severity=1.00
        # base_coefficient=1.000; backfire_base=30; per_magnitude=0.500
        #
        # Low room:  celestial magnitude 10 → 30 + round(10×0.5) = 35
        # High room: celestial magnitude 80 → 30 + round(80×0.5) = 70
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
        # Discovery row exists (first earner in this fresh per-test state).
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
