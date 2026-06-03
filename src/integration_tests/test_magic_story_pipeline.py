"""End-to-end pipeline test for the magic-story slice.

Validates the REAL production path introduced by the 2026-05-16 resonance-environment
universal-path spec:

OPPOSED path (no flow/trigger):
  Abyssal-aura caster uses an Abyssal-affinity technique in a Celestial cascade room
  → use_technique orchestrator Step 10 calls resonance_environment_for_cast(...)
  → OPPOSED REJECT interaction → endure_hallowed_ground check at backfire_difficulty
  → select_consequence_from_result over the seeded ConsequencePool
  → apply_resolution applies the per-CheckOutcome injury ConditionTemplate(s)
  → condition applied → beat satisfies → story progresses → achievement granted.

ALIGNED path (presence-tied, movement hook):
  Abyssal caster moves into Abyssal-cascade room
  → at_post_move fires refresh_resonance_alignment(character_sheet=sheet_data)
  → ALIGNED AMPLIFY interaction → band-selected boon ConditionTemplate applied.
  Move out → buff cleared. No check, no story movement.

Quiescent path:
  CharacterSheet with no CharacterAura → resonance_environment_for_cast and
  refresh_resonance_alignment return inert immediately (magical_profile returns None).

CORRUPT stub:
  Strong abyssal caster in weak primal room → primitive returns CASTER_DOMINANT/CORRUPT
  → cast service treats it as inert (no condition applied), direction still computed.

Discovery semantics:
  First earner of Hallowed-Hardened gets a Discovery row; second earner does not.

Cascade math for the Low celestial room (magnitude=10):
  AffinityInteraction(Abyssal→Celestial): OPPOSED, REJECT, severity=1.00
  caster_alignment = aura.abyssal / 100 = 100/100 = 1.0
  raw = 10 * 1.0 * 1.00 * base_coefficient(1.000) = 10.0
  magnitude = round(10.0) = 10
  backfire_difficulty = 30 + round(10 * 0.500) = 35

Cascade math for the High celestial room (magnitude=80):
  magnitude = 80 (same affinity/severity/alignment)
  backfire_difficulty = 30 + round(80 * 0.500) = 70

ALIGNED room (Abyssal/Dissolution, magnitude=60):
  60 >= HIGH band threshold (min_magnitude=40) → "Abyssal Resonance — Deep Attunement"

Test data dependencies (seeded by seed_starter_magic_story):
- ConditionTemplate "Singed", "Burning", "Tempered Against Light",
  "Hallowed Burn", "Cast Disrupted"
- ConditionTemplate "Abyssal Resonance — Minor Attunement" (min_magnitude=1)
- ConditionTemplate "Abyssal Resonance — Deep Attunement" (min_magnitude=40)
- ResonanceAlignmentBoonTier rows on pair #5 (Abyssal→Abyssal)
- Room "The Hallowed Threshold (Low)"   — Celestial cascade magnitude 10
- Room "The Hallowed Threshold (High)"  — Celestial cascade magnitude 80
- Room "The Resonant Sanctum (Aligned)" — Abyssal cascade magnitude 60
- AffinityInteraction (Abyssal→Celestial) OPPOSED/REJECT/severity=1.00  (pair #4)
- AffinityInteraction (Abyssal→Abyssal)  ALIGNED/AMPLIFY/severity=1.00  (pair #5)
- AffinityInteraction (Abyssal→Primal)   OPPOSED/CORRUPT/aggressor=caster (pair #6)
- ResonanceEnvironmentConfig (base_coefficient=1.000, caster_power_scalar=0.500,
  backfire_base_difficulty=30, backfire_difficulty_per_magnitude=0.500, balanced_band=10)
- ConsequencePool for pair #4 with 4 Consequence rows keyed by CheckOutcome
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
from world.conditions.models import ConditionInstance
from world.magic.constants import AffinityInteractionKind, ResonanceDirection
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAuraFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.magic.models.resonance_environment import ResonanceAlignmentBoonTier
from world.magic.services.resonance_environment import evaluate_resonance_environment
from world.magic.services.techniques import use_technique
from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin
from world.traits.models import CheckOutcome


class MagicStoryPipelineTests(ResonanceCacheIsolationMixin, EvenniaTestCase):
    """Full pipeline: Abyssal caster + Abyssal technique → OPPOSED resonance backfire
    via Step 10 in use_technique orchestrator → condition → beat → story → achievement.

    Cache-sensitive rows (AffinityInteraction, ResonanceAlignmentBoonTier) are
    created by seed_starter_magic_story() inside setUpTestData. Because
    ResonanceCacheIsolationMixin.setUp() clears the manager caches BEFORE super().setUp(),
    and setUpTestData runs once per class (before any setUp call), the cache is cleared
    fresh before each test — which forces a real DB load on first access. This is the
    correct isolation pattern: setUpTestData populates the DB, setUp clears the cache,
    the test re-warms from clean state.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        seed_starter_magic_story()

        from evennia.objects.models import ObjectDB

        from world.conditions.models import ConditionTemplate
        from world.magic.models.affinity import Resonance
        from world.stories.models import Story

        # Store PKs only for Evennia ObjectDB instances — they carry a DbHolder which is
        # not deepcopy-safe (Django's setUpTestData wraps class attrs in deepcopy when
        # accessed from instance methods). Re-fetching by PK in setUp avoids the error.
        # SharedMemoryModel instances (ConditionTemplate, Resonance, Story) are copyable.
        cls.singed_template = ConditionTemplate.objects.get(name="Singed")
        cls.tempered_template = ConditionTemplate.objects.get(name="Tempered Against Light")
        cls.burning_template = ConditionTemplate.objects.get(name="Burning")
        cls.hallowed_burn_template = ConditionTemplate.objects.get(name="Hallowed Burn")
        cls.cast_disrupted_template = ConditionTemplate.objects.get(name="Cast Disrupted")

        # ALIGNED boon templates seeded by T13
        cls.minor_attunement_template = ConditionTemplate.objects.get(
            name="Abyssal Resonance — Minor Attunement"
        )
        cls.deep_attunement_template = ConditionTemplate.objects.get(
            name="Abyssal Resonance — Deep Attunement"
        )

        # Store PKs for Evennia ObjectDB rooms — re-fetched in setUp to avoid DbHolder deepcopy.
        # Low room: Celestial cascade magnitude 10  → backfire_difficulty = 35
        cls.low_room_pk = (
            ObjectDB.objects.filter(
                db_key="The Hallowed Threshold (Low)",
                db_typeclass_path="typeclasses.rooms.Room",
            )
            .values_list("pk", flat=True)
            .first()
        )

        # High room: Celestial cascade magnitude 80 → backfire_difficulty = 70
        cls.high_room_pk = (
            ObjectDB.objects.filter(
                db_key="The Hallowed Threshold (High)",
                db_typeclass_path="typeclasses.rooms.Room",
            )
            .values_list("pk", flat=True)
            .first()
        )

        # Aligned room: Abyssal cascade magnitude 60 → Deep Attunement (min_magnitude=40)
        cls.aligned_room_pk = (
            ObjectDB.objects.filter(
                db_key="The Resonant Sanctum (Aligned)",
                db_typeclass_path="typeclasses.rooms.Room",
            )
            .values_list("pk", flat=True)
            .first()
        )

        cls.story = Story.objects.get(title="The Hallowed Threshold")

        # The seeded Abyssal "Dissolution" resonance — used to wire the technique gift.
        cls.dissolution_resonance = Resonance.objects.get(name="Dissolution")

    def setUp(self) -> None:
        super().setUp()  # ResonanceCacheIsolationMixin.setUp() clears caches first

        from evennia.objects.models import ObjectDB

        # Re-fetch Evennia ObjectDB rooms by PK to get live instances (not deepcopy wrappers).
        # The DbHolder on ObjectDB instances is not deepcopy-safe; storing PKs in
        # setUpTestData and re-fetching here avoids the Django TestCase deepcopy error.
        self.low_room = ObjectDB.objects.get(pk=self.low_room_pk)
        self.high_room = ObjectDB.objects.get(pk=self.high_room_pk)
        self.aligned_room = ObjectDB.objects.get(pk=self.aligned_room_pk)

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

        # Place caster in the low room by default (most OPPOSED subtests start here).
        # No apply_condition("Magically Attuned") — that baseline condition is deleted.
        # The production path is gated on CharacterAura presence alone (magical_profile).
        self.caster.location = self.low_room
        self.caster.save()

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

    def _boon_condition_template_pks(self) -> set[int]:
        """Return PKs of all seeded resonance-alignment boon templates."""
        return {t.pk for t in ResonanceAlignmentBoonTier.objects.boon_condition_templates()}

    def _boon_instances_on_caster(self) -> list[ConditionInstance]:
        """Return ConditionInstance rows on caster whose template is a boon template."""
        boon_pks = self._boon_condition_template_pks()
        return list(
            ConditionInstance.objects.filter(
                target=self.caster,
                condition__pk__in=boon_pks,
            )
        )

    # -------------------------------------------------------------------------
    # T0-T7: parametrized across all 8 outcome × intensity combinations
    # -------------------------------------------------------------------------

    # NOTE: A strength-50 caster overpowers (defiles) a magnitude-10 celestial place;
    # low-difficulty celestial *rejection* is unreachable for a dominant Abyssal caster
    # by design (#525). The low-room scenario is now covered as defilement in
    # test_defile_celestial_place_*. Only the 4 high-room rows remain below.
    @parameterized.expand(
        [
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
    def test_opposed_matrix(  # noqa: PLR0913
        self,
        test_id: str,  # noqa: ARG002
        intensity: str,
        outcome_name: str,
        expected_condition: str,
        expected_episode: str,
        expected_achievement: str | None,
        expected_difficulty: int,
    ) -> None:
        """Cast technique → resonance backfire (REAL Step 10 path) → condition → beat → story.

        Also asserts achievement when expected_achievement is not None.

        Parametrized across 4 CheckOutcomes × 2 intensity tiers = 8 subtests.

        Low room (celestial mag 10):  backfire_difficulty = 30 + round(10 × 0.5) = 35
        High room (celestial mag 80): backfire_difficulty = 30 + round(80 × 0.5) = 70

        The caster has an Abyssal CharacterAura and an Abyssal Technique.
        use_technique orchestrator Step 10 calls resonance_environment_for_cast,
        which runs an OPPOSED check (endure_hallowed_ground) against the seeded pool
        and applies the correct injury ConditionTemplate per CheckOutcome outcome.
        No flow, no trigger, no "Magically Attuned" — this is the production path.
        """
        self._place_caster_in(intensity)

        # ------------------------------------------------------------------
        # T0: Pre-state assertions
        # ------------------------------------------------------------------
        from world.achievements.models import CharacterAchievement
        from world.stories.constants import BeatOutcome
        from world.stories.models import Beat

        # No reaction conditions exist yet (Magically Attuned was removed).
        self.assertEqual(
            ConditionInstance.objects.filter(target=self.caster).count(),
            0,
            "No ConditionInstances should exist on caster before cast",
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
        # force_check_outcome intercepts the NEXT perform_check call, which
        # happens inside resonance_environment_for_cast (Step 10 of orchestrator).
        # The capture records check_type + target_difficulty.
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
        # T3: Expected reaction condition applied to caster via Step 10
        #
        # resonance_environment_for_cast → select_consequence_from_result
        # over the seeded ConsequencePool → apply_resolution applies the
        # APPLY_CONDITION effect targeting the caster.
        #
        # For Critical Failure: also assert "Cast Disrupted" was applied.
        # ------------------------------------------------------------------
        from world.conditions.models import ConditionTemplate

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
    # T8: ALIGNED amplification — real movement, boon applied, no check, no story movement
    # -------------------------------------------------------------------------

    def test_aligned_amplification(self) -> None:
        """Abyssal caster moves into Abyssal Sanctum (ALIGNED/AMPLIFY) → boon applied.

        Uses the REAL movement hook (at_post_move) rather than a direct service call.
        magnitude=60 ≥ HIGH band threshold (min_magnitude=40) → "Abyssal Resonance —
        Deep Attunement" is selected. No perform_check is ever issued (ALIGNED path does
        not trigger backfire). StoryProgress remains at "Stepping Into Light" — ALIGNED
        does not satisfy any hallowed-threshold beat.

        Assertions:
          - "Abyssal Resonance — Deep Attunement" ConditionInstance on caster.
          - Exactly one boon ConditionInstance (no stacking).
          - No OPPOSED reaction conditions applied.
          - StoryProgress still at "Stepping Into Light".
          - force_check_outcome capture records no check was intercepted.
        """
        # Place caster in aligned room and fire at_post_move (real hook).
        self.caster.db_location = self.aligned_room
        self.caster.save(update_fields=["db_location"])

        forced_outcome = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(forced_outcome) as capture:
            self.caster.at_post_move(source_location=self.low_room)

        # No perform_check was called.
        self.assertIsNone(
            capture.target_difficulty,
            "ALIGNED path must not call perform_check; force_check_outcome should be unused",
        )

        # "Abyssal Resonance — Deep Attunement" (band = HIGH, min_magnitude=40,
        # seeded Abyssal Sanctum magnitude=60 ≥ 40) must be applied.
        boon_instances = self._boon_instances_on_caster()
        self.assertEqual(
            len(boon_instances),
            1,
            "Expected exactly one boon ConditionInstance after at_post_move into aligned room",
        )
        self.assertEqual(
            boon_instances[0].condition_id,
            self.deep_attunement_template.pk,
            "Expected 'Abyssal Resonance — Deep Attunement' (HIGH band, magnitude 60 ≥ 40)",
        )

        # No OPPOSED reaction conditions should have been applied.
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

        # StoryProgress must remain at "Stepping Into Light".
        self.progress.refresh_from_db()
        self.assertEqual(
            self.progress.current_episode,
            self.episode_1,
            "StoryProgress must remain at 'Stepping Into Light' after ALIGNED move",
        )

    def test_aligned_move_out_removes_buff(self) -> None:
        """Moving OUT of the aligned room clears the boon (at_post_move into non-aligned room).

        Step 1: move INTO aligned room → Deep Attunement buff applied.
        Step 2: move INTO non-aligned (low celestial) room → buff cleared by refresh.

        No check, no story movement on either step.
        """

        # Step 1: apply buff by firing at_post_move into the aligned room.
        self.caster.db_location = self.aligned_room
        self.caster.save(update_fields=["db_location"])
        self.caster.at_post_move(source_location=self.low_room)

        boon_instances = self._boon_instances_on_caster()
        self.assertEqual(len(boon_instances), 1, "Expected buff after move into aligned room")
        self.assertEqual(boon_instances[0].condition_id, self.deep_attunement_template.pk)

        # Step 2: move to the non-aligned (Celestial) low room → buff removed.
        self.caster.db_location = self.low_room
        self.caster.save(update_fields=["db_location"])
        self.caster.at_post_move(source_location=self.aligned_room)

        boon_instances_after = self._boon_instances_on_caster()
        self.assertEqual(
            len(boon_instances_after),
            0,
            "Expected boon removed after at_post_move into non-aligned (celestial) room",
        )

    def test_aligned_no_stacking_on_double_move(self) -> None:
        """Two consecutive at_post_move calls into the same aligned room → exactly one buff.

        Idempotency guarantee: refresh_resonance_alignment clears then re-applies,
        so calling it twice must not create two ConditionInstances.
        """
        self.caster.db_location = self.aligned_room
        self.caster.save(update_fields=["db_location"])

        self.caster.at_post_move(source_location=self.low_room)
        self.caster.at_post_move(source_location=self.aligned_room)  # second fire

        boon_instances = self._boon_instances_on_caster()
        self.assertEqual(
            len(boon_instances),
            1,
            "Expected exactly one boon ConditionInstance after two at_post_move calls "
            "(no stacking)",
        )

    # -------------------------------------------------------------------------
    # T9: Inert short-circuit — untagged room, no interaction → no effect
    # -------------------------------------------------------------------------

    def test_inert_short_circuit(self) -> None:
        """Caster in a room with no resonance cascade → primitive returns inert, no effect.

        The room has no LocationValueModifier rows (key_type=RESONANCE), so
        evaluate_resonance_environment returns inert immediately.
        resonance_environment_for_cast returns inert — no condition applied.

        Assertions:
          - No ConditionInstance of any kind on caster.
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

        forced_outcome = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(forced_outcome) as capture:
            use_technique(
                character=self.caster,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="resolve_result"),
            )

        # No check was called — inert path short-circuits before perform_check.
        self.assertIsNone(
            capture.target_difficulty,
            "Inert path must not call perform_check",
        )

        # No conditions applied (no Magically Attuned either — that was removed).
        post_cast_count = ConditionInstance.objects.filter(target=self.caster).count()
        self.assertEqual(
            post_cast_count,
            0,
            "No ConditionInstances should exist after inert cast in untagged room",
        )

        # StoryProgress unchanged.
        self.progress.refresh_from_db()
        self.assertEqual(
            self.progress.current_episode,
            self.episode_1,
            "StoryProgress must remain at 'Stepping Into Light' after inert cast",
        )

    # -------------------------------------------------------------------------
    # T10: Quiescent — no CharacterAura → magical_profile returns None → inert
    # -------------------------------------------------------------------------

    def test_quiescent_no_aura_cast_is_inert(self) -> None:
        """CharacterSheet with no CharacterAura → resonance_environment_for_cast is a no-op.

        magical_profile(character_sheet) returns None when no CharacterAura exists.
        resonance_environment_for_cast short-circuits at the predicate gate —
        no check, no condition, no error.

        This is the Quiescent case: an NPC sheet or not-yet-finalized character
        has no aura and thus no resonance-environment reaction.
        """
        from world.magic.models.aura import CharacterAura

        # Create a sheet with no aura — explicitly delete any that might exist.
        quiescent_sheet = CharacterSheetFactory()
        CharacterAura.objects.filter(character=quiescent_sheet.character).delete()
        quiescent_sheet.character.location = self.low_room
        quiescent_sheet.character.save()

        # Build technique and anima so use_technique can proceed.
        CharacterAnimaFactory(character=quiescent_sheet.character, current=20, maximum=20)

        forced_outcome = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(forced_outcome) as capture:
            use_technique(
                character=quiescent_sheet.character,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="resolve_result"),
            )

        # Quiescent → no check issued.
        self.assertIsNone(
            capture.target_difficulty,
            "Quiescent caster (no aura) must not call perform_check",
        )

        # No conditions applied.
        self.assertEqual(
            ConditionInstance.objects.filter(target=quiescent_sheet.character).count(),
            0,
            "No ConditionInstances should exist after quiescent cast",
        )

    def test_quiescent_no_aura_move_is_inert(self) -> None:
        """CharacterSheet with no CharacterAura → refresh_resonance_alignment is a no-op.

        magical_profile returns None → refresh returns immediately after the initial
        boon-clear step. No boon applied, no error.
        """
        from world.magic.models.aura import CharacterAura

        quiescent_sheet = CharacterSheetFactory()
        CharacterAura.objects.filter(character=quiescent_sheet.character).delete()

        quiescent_sheet.character.db_location = self.aligned_room
        quiescent_sheet.character.save(update_fields=["db_location"])

        # Fire the hook directly.
        quiescent_sheet.character.at_post_move(source_location=self.low_room)

        boon_pks = self._boon_condition_template_pks()
        self.assertEqual(
            ConditionInstance.objects.filter(
                target=quiescent_sheet.character,
                condition__pk__in=boon_pks,
            ).count(),
            0,
            "Quiescent character (no aura) must not receive any boon ConditionInstance",
        )

    # -------------------------------------------------------------------------
    # T11: Defilement — real CASTER_DOMINANT defilement pipeline (issue #525)
    # -------------------------------------------------------------------------

    def _build_primal_room(self) -> tuple[object, object, object]:
        """Helper: create a weak Primal room (magnitude=10) + return (room, profile, resonance).

        Pair #6 (Abyssal→Primal): OPPOSED / CORRUPT / caster_dominance_defiles=True.
        caster_strength(50) - place_magnitude(10) = 40 > balanced_band(10) → CASTER_DOMINANT.
        """
        from evennia.utils import create as evennia_create

        from evennia_extensions.models import RoomProfile
        from world.magic.models.affinity import Affinity, Resonance
        from world.magic.services.gain import tag_room_resonance

        primal_affinity = Affinity.objects.get(name="Primal")
        primal_resonance, _ = Resonance.objects.get_or_create(
            name="Decay (pipeline test)",
            defaults={"affinity": primal_affinity},
        )
        primal_room = evennia_create.create_object(
            typeclass="typeclasses.rooms.Room",
            key="Weak Primal Ground (pipeline test)",
            nohome=True,
        )
        primal_profile, _ = RoomProfile.objects.get_or_create(objectdb=primal_room)
        modifier = tag_room_resonance(primal_profile, primal_resonance)
        modifier.value = 10
        modifier.save(update_fields=["value"])
        return primal_room, primal_profile, primal_resonance

    def test_defile_primal_place(self) -> None:
        """Strong Abyssal caster (aura=100) in weak Primal room (mag=10) → CASTER_DOMINANT CORRUPT.

        Math:
          caster_strength = 100 × 0.500 = 50.0
          place_magnitude = 10
          50 - 10 = 40 > balanced_band(10) → CASTER_DOMINANT

        Pair #6 (Abyssal→Primal): OPPOSED / CORRUPT / caster_dominance_defiles=True.
        defile_place_for_cast is called by use_technique Step 10, which:
          1. Degrades: primal resonance effective_value 10 → 4 (−6).
          2. Spreads: Dissolution modifier with source="defilement" += 6 on the room.
          3. Accrues: CharacterResonance.corruption_current for Dissolution rises.

        Second cast: primal floors at 0 (4−6 floored), dissolution grows to 12.
        After 2 casts the room is more Abyssal than Primal — corrupted ground.
        """
        from world.locations.models import LocationValueModifier
        from world.locations.services import effective_value
        from world.magic.models.aura import CharacterResonance
        from world.magic.services.resonance_environment import (
            get_resonance_environment_config,
        )

        primal_room, primal_profile, primal_resonance = self._build_primal_room()
        self.caster.location = primal_room
        self.caster.save()

        # --- Primitive assertion: CASTER_DOMINANT / CORRUPT ---
        cfg = get_resonance_environment_config()
        primitive = evaluate_resonance_environment(
            caster=self.caster, room=primal_room, technique=self.technique
        )
        caster_strength = float(Decimal("100.00") * cfg.caster_power_scalar)
        self.assertGreater(
            caster_strength - 10,
            cfg.balanced_band,
            "Math pre-check: caster_strength − place_magnitude must exceed balanced_band",
        )
        self.assertEqual(
            primitive.direction,
            ResonanceDirection.CASTER_DOMINANT,
            "evaluate_resonance_environment must return CASTER_DOMINANT for strong abyssal vs "
            "weak primal",
        )
        self.assertEqual(
            primitive.kind,
            AffinityInteractionKind.CORRUPT,
            "evaluate_resonance_environment must return kind=CORRUPT for Abyssal→Primal",
        )

        # --- First cast ---
        forced_outcome = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(forced_outcome) as capture:
            use_technique(
                character=self.caster,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="resolve_result"),
            )

        # No backfire check on the defilement path.
        self.assertIsNone(
            capture.target_difficulty,
            "CASTER_DOMINANT CORRUPT must not call perform_check — defilement path, not backfire",
        )

        # 1. Degrade: primal resonance effective_value dropped by defile_degrade_per_cast(6)
        primal_ev_after_1 = effective_value(primal_room, resonance=primal_resonance)
        self.assertEqual(
            primal_ev_after_1,
            4,  # 10 − 6 = 4
            f"Primal effective_value must be 4 after first cast (was 10, degrade=6), "
            f"got {primal_ev_after_1}",
        )

        # 2. Spread: Dissolution gets a room-level source="defilement" modifier of value=6
        defile_source = "defilement"
        dissolution_mod = LocationValueModifier.objects.filter(
            room_profile=primal_profile,
            resonance=self.dissolution_resonance,
            source=defile_source,
        ).first()
        self.assertIsNotNone(
            dissolution_mod,
            "Dissolution spread: a room-level source='defilement' LocationValueModifier must exist "
            "after first cast",
        )
        self.assertEqual(
            dissolution_mod.value,
            6,  # defile_spread_per_cast=6
            f"Dissolution defilement modifier value must be 6 after first cast, "
            f"got {dissolution_mod.value}",
        )
        dissolution_ev_after_1 = effective_value(primal_room, resonance=self.dissolution_resonance)
        self.assertEqual(
            dissolution_ev_after_1,
            6,
            f"Dissolution effective_value must be 6 after first cast, got {dissolution_ev_after_1}",
        )

        # 3. Corruption: CharacterResonance.corruption_current for Dissolution rose.
        #    defile_corruption_per_cast=2 → at least 1 unit accrued (CORRUPTION_ACCRUING emitted).
        char_res = CharacterResonance.objects.filter(
            character_sheet=self.sheet,
            resonance=self.dissolution_resonance,
        ).first()
        self.assertIsNotNone(
            char_res,
            "CharacterResonance row for Dissolution must exist after defilement cast "
            "(accrue fired)",
        )
        # corruption_current includes both per-cast baseline AND defilement increment.
        # Assert it is at least the defilement amount (defile_corruption_per_cast=2).
        self.assertGreaterEqual(
            char_res.corruption_current,
            cfg.defile_corruption_per_cast,
            f"corruption_current must be >= defile_corruption_per_cast"
            f"({cfg.defile_corruption_per_cast}) after first cast "
            f"(CORRUPTION_ACCRUING with DEFILEMENT source fired), "
            f"got {char_res.corruption_current}",
        )

        # After the first cast the room has ALREADY FLIPPED to Abyssal-dominant:
        # Dissolution=6 > Primal=4. On the second cast, evaluate_resonance_environment
        # finds dominant affinity = Abyssal (the caster's own affinity), so pair #5
        # (Abyssal→Abyssal = ALIGNED/AMPLIFY) fires — not an OPPOSED/CORRUPT path.
        # defile_place_for_cast therefore returns early (direction != CASTER_DOMINANT),
        # and neither primal nor dissolution values change further.
        # This is correct game physics: defilement succeeds by flipping the room;
        # once flipped, further casts are ALIGNED (the caster is now "home").

        # After first cast: Dissolution already dominates over Primal (corrupted ground).
        self.assertGreater(
            effective_value(primal_room, resonance=self.dissolution_resonance),
            effective_value(primal_room, resonance=primal_resonance),
            "After 1 cast, Dissolution (6) must exceed Primal (4) — room already flipped "
            "to Abyssal-dominant (corrupted ground achieved in one cast)",
        )

    def test_defile_celestial_place_replaces_rejection(self) -> None:
        """Strong Abyssal caster in low celestial room (mag=10) → CASTER_DOMINANT defiles, no burn.

        Math: 50 − 10 = 40 > balanced_band(10) → CASTER_DOMINANT on pair #4
        (Abyssal→Celestial, caster_dominance_defiles=True).
        Backfire (Hallowed Burn) is suppressed — _is_opposed_backfire returns False.

        Assertions:
          - Celestial "Light" resonance effective_value dropped by 6.
          - Dissolution spread modifier with source="defilement" exists, value=6.
          - CharacterResonance.corruption_current for Dissolution rose (CORRUPTION_ACCRUING fired).
          - No Hallowed Burn ConditionInstance applied (backfire suppressed).
          - No injury condition of any kind applied by this cast.
        """
        from world.locations.models import LocationValueModifier
        from world.locations.services import effective_value
        from world.magic.models.affinity import Resonance
        from world.magic.models.aura import CharacterResonance
        from world.magic.services.resonance_environment import (
            get_resonance_environment_config,
        )

        # Caster is already in self.low_room (celestial Light magnitude=10) from setUp.
        cfg = get_resonance_environment_config()

        # Fetch the Celestial "Light" resonance tagged on low_room.
        light_resonance = Resonance.objects.get(name="Light")

        # Pre-cast: effective_value of Light on low_room = 10.
        light_ev_before = effective_value(self.low_room, resonance=light_resonance)
        self.assertEqual(light_ev_before, 10, "Light resonance baseline must be 10 in low_room")

        # Cast once.
        forced_outcome = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(forced_outcome) as capture:
            use_technique(
                character=self.caster,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="resolve_result"),
            )

        # Backfire check must NOT have fired (CASTER_DOMINANT defiles, no rejection).
        self.assertIsNone(
            capture.target_difficulty,
            "CASTER_DOMINANT on pair #4 must suppress the OPPOSED backfire check; "
            "no perform_check should have been called",
        )

        # 1. Celestial resonance effective_value dropped by defile_degrade_per_cast(6): 10 → 4.
        light_ev_after = effective_value(self.low_room, resonance=light_resonance)
        self.assertEqual(
            light_ev_after,
            4,  # 10 − 6 = 4
            f"Light effective_value must drop to 4 after defilement cast (was 10, degrade=6), "
            f"got {light_ev_after}",
        )

        # 2. Dissolution spread: room-level source="defilement" modifier, value=6.
        low_room_profile = self.low_room.room_profile
        defile_source = "defilement"
        dissolution_mod = LocationValueModifier.objects.filter(
            room_profile=low_room_profile,
            resonance=self.dissolution_resonance,
            source=defile_source,
        ).first()
        self.assertIsNotNone(
            dissolution_mod,
            "Dissolution spread: room-level source='defilement' modifier must exist after cast",
        )
        self.assertEqual(
            dissolution_mod.value,
            6,
            f"Dissolution spread modifier must be 6 after first cast, got {dissolution_mod.value}",
        )

        # 3. Corruption: CharacterResonance for Dissolution rose (DEFILEMENT source fired).
        char_res = CharacterResonance.objects.filter(
            character_sheet=self.sheet,
            resonance=self.dissolution_resonance,
        ).first()
        self.assertIsNotNone(
            char_res,
            "CharacterResonance for Dissolution must exist after defilement cast",
        )
        self.assertGreaterEqual(
            char_res.corruption_current,
            cfg.defile_corruption_per_cast,
            f"corruption_current must be >= {cfg.defile_corruption_per_cast} "
            f"(CORRUPTION_ACCRUING with DEFILEMENT source fired), "
            f"got {char_res.corruption_current}",
        )

        # 4. No Hallowed Burn — backfire suppressed when defilement fires.
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=self.caster,
                condition=self.hallowed_burn_template,
            ).exists(),
            "Hallowed Burn must NOT be applied when CASTER_DOMINANT defiles the place (#525)",
        )

        # 5. No injury condition of any kind applied by this cast.
        injury_templates = [
            self.singed_template,
            self.burning_template,
            self.tempered_template,
            self.hallowed_burn_template,
            self.cast_disrupted_template,
        ]
        for tmpl in injury_templates:
            self.assertFalse(
                ConditionInstance.objects.filter(
                    target=self.caster,
                    condition=tmpl,
                ).exists(),
                f"Injury condition '{tmpl.name}' must NOT be applied on the defilement path",
            )

    def test_weak_abyssal_caster_celestial_still_burned(self) -> None:
        """Weak-dominant caster (ENVIRONMENT_DOMINANT in high room) still backfires normally.

        Caster in high_room (Celestial magnitude=80):
          caster_strength(50) - 80 = −30; 80 - 50 = 30 > balanced_band(10) → ENVIRONMENT_DOMINANT.
        Pair #4 (Abyssal→Celestial) with caster_dominance_defiles=True but direction is
        ENVIRONMENT_DOMINANT → _is_opposed_backfire returns True → normal backfire pipeline fires.

        Force Critical Failure → Hallowed Burn applied.
        No source="defilement" modifier rows appear on the high_room's profile.
        Caster's Dissolution corruption_current did NOT rise from defilement.
        """
        from world.locations.models import LocationValueModifier

        # Place caster in the high celestial room.
        self.caster.location = self.high_room
        self.caster.save()

        high_room_profile = self.high_room.room_profile
        defile_source = "defilement"

        # Cast with Critical Failure forced → backfire → Hallowed Burn applied.
        crit_fail = CheckOutcome.objects.get(name="Critical Failure")
        with force_check_outcome(crit_fail):
            use_technique(
                character=self.caster,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="resolve_result"),
            )

        # Hallowed Burn must be applied (normal backfire path, ENVIRONMENT_DOMINANT).
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.caster,
                condition=self.hallowed_burn_template,
            ).exists(),
            "Hallowed Burn must be applied on Critical Failure in ENVIRONMENT_DOMINANT room "
            "(high celestial, not CASTER_DOMINANT)",
        )

        # No source="defilement" modifier rows on the high room's profile.
        self.assertFalse(
            LocationValueModifier.objects.filter(
                room_profile=high_room_profile,
                source=defile_source,
            ).exists(),
            "No source='defilement' LocationValueModifier must exist on the high_room "
            "(backfire fired, not defilement)",
        )
        # The absence of any source='defilement' modifier row is the definitive gate that
        # defile_place_for_cast was a no-op here (baseline per-cast corruption from
        # accrue_corruption_for_cast is unrelated and intentionally not asserted on).

    def test_primal_caster_does_not_defile_celestial(self) -> None:
        """Negative control: Primal-aura caster in low celestial room → no defilement.

        Pair #7 (Primal→Celestial): OPPOSED / REJECT / caster_dominance_defiles=False.
        _compute_direction returns ENVIRONMENT_DOMINANT (flag=False, kind≠CORRUPT).
        _is_opposed_backfire returns True → normal backfire fires (not defilement).
        No source="defilement" modifier rows appear on low_room.

        This proves only the Abyss defiles (the lore boundary holds mechanically).
        """
        from world.locations.models import LocationValueModifier
        from world.magic.factories import (
            CharacterAnimaFactory,
            CharacterAuraFactory,
            GiftFactory,
            TechniqueFactory,
        )
        from world.magic.models.affinity import Affinity, Resonance

        defile_source = "defilement"
        low_room_profile = self.low_room.room_profile

        # Build a Primal-aura caster with a Primal-resonance technique.
        primal_sheet = CharacterSheetFactory()
        primal_caster = primal_sheet.character

        CharacterAuraFactory(
            character=primal_caster,
            celestial=Decimal("0.00"),
            primal=Decimal("100.00"),
            abyssal=Decimal("0.00"),
        )
        CharacterAnimaFactory(character=primal_caster, current=20, maximum=20)

        # Seed a Primal resonance and wire it into a technique.
        primal_affinity = Affinity.objects.get(name="Primal")
        primal_resonance, _ = Resonance.objects.get_or_create(
            name="Decay (pipeline test)",
            defaults={"affinity": primal_affinity},
        )
        primal_gift = GiftFactory(name="Primal Arts (defilement test)")
        primal_gift.resonances.set([primal_resonance])
        primal_technique = TechniqueFactory(
            name="Primal Strike (defilement test)",
            gift=primal_gift,
            intensity=1,
            control=1,
            anima_cost=1,
        )

        primal_caster.location = self.low_room
        primal_caster.save()

        # Cast — force Success so we get a deterministic outcome.
        forced_outcome = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(forced_outcome):
            use_technique(
                character=primal_caster,
                technique=primal_technique,
                resolve_fn=MagicMock(return_value="resolve_result"),
            )

        # No source="defilement" modifier rows on low_room — Primal casters do not defile.
        self.assertFalse(
            LocationValueModifier.objects.filter(
                room_profile=low_room_profile,
                source=defile_source,
            ).exists(),
            "Primal caster must NOT produce source='defilement' modifier rows on low_room "
            "(only Abyssal CASTER_DOMINANT casters defile — pair #7 flag=False)",
        )

    # -------------------------------------------------------------------------
    # T12: Second-earner Discovery semantics
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

        NOTE (#525): both casters are placed in the HIGH celestial room (magnitude=80,
        ENVIRONMENT_DOMINANT). The low_room (magnitude=10) now DEFILES instead of
        backfiring for a 50-strength Abyssal caster — no backfire condition is applied
        there. The high room remains ENVIRONMENT_DOMINANT and fires the normal backfire
        pipeline (Tempered Against Light on Critical Success → Hallowed-Hardened).
        """
        from world.achievements.models import Achievement, CharacterAchievement, Discovery

        hallowed_hardened = Achievement.objects.get(name="Hallowed-Hardened")
        crit_success = CheckOutcome.objects.get(name="Critical Success")

        # ------------------------------------------------------------------
        # First caster: self.caster from setUp — already has an Abyssal aura,
        # technique, anima. Cast in the HIGH celestial room (magnitude=80,
        # ENVIRONMENT_DOMINANT) where normal OPPOSED backfire fires.
        # NOTE: the low_room (magnitude=10) now DEFILES instead of backfiring —
        # a 50-strength Abyssal caster overpowers it (#525). The high room
        # (magnitude=80) stays ENVIRONMENT_DOMINANT (80−50=30 > balanced_band=10)
        # so the backfire path (Tempered Against Light on Crit Success) is intact.
        # Cast → Critical Success → Tempered Against Light
        # applied → stat incremented → Hallowed-Hardened granted → Discovery created.
        # ------------------------------------------------------------------
        self._place_caster_in("high")

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
        # Second caster: independent CharacterSheet + Abyssal CharacterAura +
        # Anima + same technique (self.technique is shared) in the high room.
        # Uses high_room (ENVIRONMENT_DOMINANT) so backfire fires normally.
        # No StoryProgress — story routing is not required for the Discovery assertion.
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

        second_caster.location = self.high_room
        second_caster.save()

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

        # Second earner is NOT the discoverer.
        self.assertIsNone(
            second_ca.discovery,
            "Second earner's CharacterAchievement.discovery must be None (not a co-discoverer)",
        )
