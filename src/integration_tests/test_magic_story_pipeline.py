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
from world.magic.constants import AffinityInteractionKind, ResonanceDirection
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAuraFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.magic.services.resonance_environment import evaluate_resonance_environment
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

    # -------------------------------------------------------------------------
    # T8: ALIGNED amplification — boon applied, no check, no story movement
    # -------------------------------------------------------------------------

    def test_aligned_amplification(self) -> None:
        """Abyssal caster in Abyssal Sanctum (ALIGNED/AMPLIFY) → Empowered boon, no backfire.

        Abyssal→Abyssal AffinityInteraction: ALIGNED / AMPLIFY / severity=1.00.
        The flow short-circuits at Step 3 (aligned_branch PASS) and applies
        "Empowered by Resonant Ground" directly — no perform_check is ever issued.

        Assertions:
          - "Empowered by Resonant Ground" ConditionInstance on caster.
          - No reaction conditions (Singed / Burning / Tempered / Hallowed Burn /
            Cast Disrupted) applied.
          - StoryProgress still at "Stepping Into Light" (ALIGNED path does not
            satisfy any hallowed-threshold beat).
          - force_check_outcome capture records no check was intercepted (the context
            manager's target_difficulty stays None when no check fires).
        """
        self._place_caster_in("aligned")

        from world.conditions.models import ConditionInstance, ConditionTemplate

        empowered_template = ConditionTemplate.objects.get(name="Empowered by Resonant Ground")

        forced_outcome = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(forced_outcome) as capture:
            use_technique(
                character=self.caster,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="resolve_result"),
            )

        # No perform_check was called — the capture should not have been exercised.
        self.assertIsNone(
            capture.target_difficulty,
            "ALIGNED branch must not call perform_check; force_check_outcome should be unused",
        )

        # "Empowered by Resonant Ground" must have been applied by the flow.
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.caster,
                condition=empowered_template,
            ).exists(),
            "'Empowered by Resonant Ground' must be applied to caster in ALIGNED room",
        )

        # No reaction/backfire conditions should have been applied.
        reaction_templates = [
            self.singed_template,
            self.burning_template,
            self.tempered_template,
            self.hallowed_burn_template,
            self.cast_disrupted_template,
        ]
        for tmpl in reaction_templates:
            self.assertFalse(
                ConditionInstance.objects.filter(
                    target=self.caster,
                    condition=tmpl,
                ).exists(),
                f"Reaction condition '{tmpl.name}' must NOT be applied in ALIGNED room",
            )

        # StoryProgress must remain at "Stepping Into Light" — ALIGNED path does not
        # satisfy any hallowed-threshold beat, so no episode transition occurs.
        self.progress.refresh_from_db()
        self.assertEqual(
            self.progress.current_episode,
            self.episode_1,
            "StoryProgress must remain at 'Stepping Into Light' after ALIGNED cast",
        )

    # -------------------------------------------------------------------------
    # T9: Inert short-circuit — untagged room, no interaction → no effect
    # -------------------------------------------------------------------------

    def test_inert_short_circuit(self) -> None:
        """Caster in a room with no resonance cascade → primitive returns inert, flow ends.

        The room has no LocationValueModifier rows (key_type=RESONANCE), so
        _get_room_resonances() returns [] and the primitive returns inert immediately.
        The flow Step 1 dict-unpacks resonance_valence="" / resonance_kind="";
        Step 2 CORRUPT check FAILs (kind is ""); Step 3 ALIGNED check FAILs (valence
        is ""); Step 4 OPPOSED check FAILs (valence is "") → END.

        Assertions:
          - No ConditionInstance of any kind on caster (not Empowered, not reaction).
          - StoryProgress still at "Stepping Into Light".
          - No perform_check called.
        """
        from evennia.utils import create as evennia_create

        from evennia_extensions.models import RoomProfile

        # Create a fresh room with no resonance tags.
        inert_room = evennia_create.create_object(
            typeclass="typeclasses.rooms.Room",
            key="Inert Test Room (no resonance)",
            nohome=True,
        )
        # Ensure RoomProfile exists (auto-created by at_object_creation, but confirm).
        RoomProfile.objects.get_or_create(objectdb=inert_room)

        self.caster.location = inert_room
        self.caster.save()

        from world.conditions.models import ConditionInstance

        forced_outcome = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(forced_outcome) as capture:
            use_technique(
                character=self.caster,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="resolve_result"),
            )

        # No check was called.
        self.assertIsNone(
            capture.target_difficulty,
            "Inert path must not call perform_check",
        )

        # No conditions applied by the flow (Magically Attuned was applied in setUp
        # and must remain the only ConditionInstance on the caster).
        post_cast_count = ConditionInstance.objects.filter(target=self.caster).count()
        self.assertEqual(
            post_cast_count,
            1,
            "Only 'Magically Attuned' (applied in setUp) should exist; inert flow adds nothing",
        )

        # StoryProgress unchanged.
        self.progress.refresh_from_db()
        self.assertEqual(
            self.progress.current_episode,
            self.episode_1,
            "StoryProgress must remain at 'Stepping Into Light' after inert cast",
        )

    # -------------------------------------------------------------------------
    # T10: CASTER_DOMINANT stub — strong abyssal caster vs weak primal room
    # -------------------------------------------------------------------------

    def test_caster_dominant_stub(self) -> None:
        """Strong abyssal caster (aura=100) in weak Primal room (mag=10) → CASTER_DOMINANT CORRUPT.

        Math:
          caster_strength = 100 * 0.500 = 50.0
          place_magnitude = 10
          caster_strength - place_magnitude = 40 > balanced_band(10) → CASTER_DOMINANT

        The seeded AffinityInteraction (Abyssal→Primal): OPPOSED / CORRUPT / aggressor=CASTER.
        The flow Step 2 (EVALUATE_EQUALS resonance_kind == "corrupt") PASSES → END.
        No condition is applied; no story movement; no perform_check.

        STUB: when defilement (CASTER_DOMINANT) is built, this caster should degrade
        the room's primal cascade magnitude and route corruption through CORRUPTION_ACCRUING
        (see spec deferred §). This test is the fill-in point.
        """
        from evennia.utils import create as evennia_create

        from evennia_extensions.models import RoomProfile
        from world.conditions.models import ConditionInstance
        from world.magic.models.affinity import Affinity, Resonance
        from world.magic.services.gain import tag_room_resonance
        from world.magic.services.resonance_environment import get_resonance_environment_config

        # Build a Primal resonance (Primal affinity is seeded by seed_canonical_affinities).
        primal_affinity = Affinity.objects.get(name="Primal")
        primal_resonance, _ = Resonance.objects.get_or_create(
            name="Decay (pipeline test)",
            defaults={"affinity": primal_affinity},
        )

        # Create a room and tag it with Primal resonance at low magnitude = 10.
        # caster_strength (50) - place_magnitude (10) = 40 > balanced_band (10) → CASTER_DOMINANT.
        primal_room = evennia_create.create_object(
            typeclass="typeclasses.rooms.Room",
            key="Weak Primal Ground (pipeline test)",
            nohome=True,
        )
        primal_profile, _ = RoomProfile.objects.get_or_create(objectdb=primal_room)
        modifier = tag_room_resonance(primal_profile, primal_resonance)
        modifier.value = 10
        modifier.save(update_fields=["value"])

        self.caster.location = primal_room
        self.caster.save()

        # --- Direct primitive assertion: verify CASTER_DOMINANT before the flow cast ---
        cfg = get_resonance_environment_config()
        primitive_result = evaluate_resonance_environment(
            caster=self.caster, room=primal_room, technique=self.technique
        )
        caster_strength = float(Decimal("100.00") * cfg.caster_power_scalar)
        # caster_strength - place_magnitude = 50.0 - 10 = 40 > balanced_band(10) → CASTER_DOMINANT
        self.assertGreater(
            caster_strength - 10,
            cfg.balanced_band,
            "Math pre-check: caster_strength - place_magnitude must exceed balanced_band",
        )
        self.assertEqual(
            primitive_result.direction,
            ResonanceDirection.CASTER_DOMINANT,
            "evaluate_resonance_environment must return CASTER_DOMINANT "
            "for strong abyssal vs weak primal",
        )
        self.assertEqual(
            primitive_result.kind,
            AffinityInteractionKind.CORRUPT,
            "evaluate_resonance_environment must return kind=CORRUPT "
            "for Abyssal→Primal interaction",
        )

        # --- Flow cast: CORRUPT branch → inert (no condition, no story movement) ---
        forced_outcome = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(forced_outcome) as capture:
            use_technique(
                character=self.caster,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="resolve_result"),
            )

        # CORRUPT is uniformly inert this slice — no perform_check.
        self.assertIsNone(
            capture.target_difficulty,
            "CASTER_DOMINANT CORRUPT must not call perform_check (flow ends at Step 2)",
        )

        # No conditions applied by the flow (Magically Attuned was applied in setUp
        # and must remain the only ConditionInstance on the caster).
        post_cast_count = ConditionInstance.objects.filter(target=self.caster).count()
        self.assertEqual(
            post_cast_count,
            1,
            "Only 'Magically Attuned' (from setUp) should exist after CASTER_DOMINANT CORRUPT cast",
        )

        # StoryProgress unchanged.
        self.progress.refresh_from_db()
        self.assertEqual(
            self.progress.current_episode,
            self.episode_1,
            "StoryProgress must remain at 'Stepping Into Light' after CASTER_DOMINANT CORRUPT cast",
        )

    # -------------------------------------------------------------------------
    # T11: Second-earner Discovery semantics
    # -------------------------------------------------------------------------

    def test_critical_success_second_earner_is_not_discoverer(self) -> None:
        """Discovery semantics: the first character to earn Hallowed-Hardened
        is the discoverer; a subsequent earner gets CharacterAchievement but
        is NOT the discoverer.

        Confirmed from world/achievements/services.py grant_achievement():
          - is_first_discovery = not CharacterAchievement.objects.filter(
                achievement=achievement).exists()
          - If first: Discovery.objects.create(achievement=achievement) →
            CharacterAchievement.objects.get_or_create(..., defaults={"discovery": discovery})
          - If second+: discovery=None → get_or_create defaults={"discovery": None}
          - Result: second earner's CharacterAchievement.discovery is None.

        Story-routing simplification: the achievement is granted via the
        condition→stat bridge (ConditionStatRule increments
        "conditions.tempered_against_light.gained" when Tempered Against
        Light is applied; _check_achievements then calls grant_achievement).
        This is independent of Story beat progression. Neither the first nor
        the second caster requires a StoryProgress for the Discovery assertion
        to be valid. The seeded StoryProgress for self.caster (from setUp)
        is present but its beat evaluation is incidental — we do not assert
        story state in this test.
        """
        from world.achievements.models import Achievement, CharacterAchievement, Discovery

        hallowed_hardened = Achievement.objects.get(name="Hallowed-Hardened")
        crit_success = CheckOutcome.objects.get(name="Critical Success")

        # ------------------------------------------------------------------
        # First caster: self.caster from setUp — already has Magically Attuned,
        # Abyssal aura, technique, anima, and is in the low room.
        # Cast → Critical Success → Tempered Against Light applied → stat
        # incremented → Hallowed-Hardened granted → Discovery created.
        # ------------------------------------------------------------------
        with force_check_outcome(crit_success):
            use_technique(
                character=self.caster,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="resolve_result"),
            )

        first_ca = CharacterAchievement.objects.get(
            character_sheet=self.sheet,
            achievement=hallowed_hardened,
        )
        self.assertIsNotNone(
            first_ca.discovery,
            "First earner's CharacterAchievement.discovery must point at the Discovery row",
        )
        discovery = Discovery.objects.get(achievement=hallowed_hardened)
        self.assertEqual(
            first_ca.discovery,
            discovery,
            "First earner's discovery FK must reference the one Discovery row",
        )

        # ------------------------------------------------------------------
        # Second caster: independent CharacterSheet + Abyssal aura + Anima +
        # Magically Attuned + same technique (self.technique is shared) in
        # the low room.  No StoryProgress — story routing is not required for
        # the Discovery assertion (see docstring).
        # ------------------------------------------------------------------
        second_sheet = CharacterSheetFactory()
        second_caster = second_sheet.character

        CharacterAuraFactory(
            character=second_caster,
            celestial=Decimal("0.00"),
            primal=Decimal("0.00"),
            abyssal=Decimal("100.00"),
        )
        CharacterAnimaFactory(character=second_caster, current=20, maximum=20)

        second_caster.location = self.low_room
        second_caster.save()

        result = apply_condition(
            target=second_caster,
            condition=self.magically_attuned,
        )
        self.assertTrue(
            result.success,
            f"Magically Attuned must apply to second caster; got: {result.message}",
        )

        with force_check_outcome(crit_success):
            use_technique(
                character=second_caster,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="resolve_result"),
            )

        # ------------------------------------------------------------------
        # Discovery assertions
        # ------------------------------------------------------------------
        # Exactly one Discovery row — no second Discovery was created.
        self.assertEqual(
            Discovery.objects.filter(achievement=hallowed_hardened).count(),
            1,
            "Only one Discovery row should exist for Hallowed-Hardened after two earners",
        )

        # Second caster earned the achievement.
        second_ca = CharacterAchievement.objects.get(
            character_sheet=second_sheet,
            achievement=hallowed_hardened,
        )

        # Second earner is NOT the discoverer: grant_achievement passes
        # defaults={"discovery": None} when is_first_discovery is False.
        self.assertIsNone(
            second_ca.discovery,
            "Second earner's CharacterAchievement.discovery must be None (not a co-discoverer)",
        )
