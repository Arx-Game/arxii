"""End-to-end signature-motif bonus journey test (#1582, Task 8).

Full journey: give the character a Motif facet → weave a TECHNIQUE thread →
select a facet-gated SignatureMotifBonus via the Task-4 service → cast via
request_technique_cast → assert:

  (a) cosmetic snippet appears in the cast pose Interaction;
  (b) bonus mechanical effect applies — flat_intensity_delta folds into cast,
      and the bonus condition lands on the caster (PG-only; @tag("postgres"));
  (c) non-qualifying bonus is rejected with SignatureBonusNotAvailable;
  (d) signing an unknown technique raises TechniqueNotOwned;
  (e) move/port — set on thread A, clear A, set on thread B (independent
      storage; explicit clear to "move").

SQLite fast tier: (a), (b-intensity), (c), (d), (e).
@tag("postgres"): (b-condition) — DISTINCT ON in the get_active_conditions path.
The 29 DISTINCT-ON failures elsewhere in magic/vitals/mechanics are pre-existing.
"""

from unittest.mock import MagicMock, patch

from django.test.utils import tag

from actions.constants import ResolutionPhase
from actions.types import PendingActionResolution, StepResult
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.services import get_active_conditions
from world.magic.constants import TargetKind
from world.magic.exceptions import SignatureBonusNotAvailable, TechniqueNotOwned
from world.magic.factories import (
    FacetFactory,
    MotifFactory,
    MotifResonanceAssociationFactory,
    MotifResonanceFactory,
    ResonanceFactory,
)
from world.magic.models import (
    SignatureMotifBonus,
    SignatureMotifBonusAppliedCondition,
    Thread,
)
from world.magic.models.techniques import ConditionTargetKind
from world.magic.services.signature import clear_signature_bonus, set_signature_bonus
from world.scenes.cast_services import request_technique_cast
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    grant_technique,
    make_benign_castable_technique,
)

# ---------------------------------------------------------------------------
# Helper: deterministic cast-resolution mock
# ---------------------------------------------------------------------------


def _deterministic_success() -> PendingActionResolution:
    """Build a PendingActionResolution with success_level=1 for cast mocking.

    Mirrors the helper in test_signature_cast.py so the PG condition-landing test
    drives through a confirmed successful resolution.
    """
    check_result = MagicMock()
    check_result.success_level = 1
    check_result.outcome_name = "Success"
    check_result.outcome = None
    main_result = StepResult(step_label="main", check_result=check_result, consequence_id=None)
    return PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=10,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )


# ---------------------------------------------------------------------------
# Shared base: fixture builder
# ---------------------------------------------------------------------------


class _SignatureMotifE2EBase(CastScenarioMixin):
    """Fixture infrastructure shared across the E2E test classes.

    Each test method calls ``_build_signature_fixture()`` to create the full
    Motif + TECHNIQUE-thread + bonus graph from scratch.  Creating per-test
    (rather than in setUpTestData) is necessary because ``set_signature_bonus``
    mutates the Thread row; Django TestCase rolls back mutations after each test
    so subsequent tests start with a clean Thread (no bonus set).
    """

    def _build_signature_fixture(
        self,
        *,
        narrative_snippet: str = "silver threads shimmer through the strike",
        flat_intensity_delta: int = 5,
        add_condition: bool = True,
    ):
        """Create the full signed-technique fixture.

        Sets up (in order):
          1. A benign castable technique, granted to the caster.
          2. A Motif on the caster's CharacterSheet with one Resonance, one
             Facet, and a MotifResonanceAssociation binding them.
          3. A SignatureMotifBonus gated on that Facet.
          4. (optionally) A SignatureMotifBonusAppliedCondition on the bonus.
          5. A TECHNIQUE-kind Thread for the technique (NO bonus set yet —
             the service call under test sets it).

        Args:
            narrative_snippet: Prose appended to the cast-outcome narration.
            flat_intensity_delta: Power bonus forwarded as power_intensity_bonus.
            add_condition: When True, attaches a SELF-targeting applied condition.

        Returns:
            (technique, thread, bonus, condition_or_None, facet, resonance)
        """
        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)
        sheet = self.caster.character_sheet

        # Motif gate: one-to-one Motif → MotifResonance → MotifResonanceAssociation.
        motif = MotifFactory(character=sheet)
        resonance = ResonanceFactory()
        facet = FacetFactory(name="MotifE2EFacet")
        motif_res = MotifResonanceFactory(motif=motif, resonance=resonance)
        MotifResonanceAssociationFactory(motif_resonance=motif_res, facet=facet)

        bonus = SignatureMotifBonus.objects.create(
            name="E2E Signed Strike",
            required_facet=facet,
            flat_intensity_delta=flat_intensity_delta,
            narrative_snippet=narrative_snippet,
        )

        condition = None
        if add_condition:
            condition = ConditionTemplateFactory(name="SignatureE2EMark", can_be_dispelled=True)
            SignatureMotifBonusAppliedCondition.objects.create(
                signature_bonus=bonus,
                condition=condition,
                target_kind=ConditionTargetKind.SELF,
                minimum_success_level=0,
                base_severity=1,
                stack_count=1,
            )

        # Thread created WITHOUT a bonus — the test drives set_signature_bonus.
        thread = Thread.objects.create(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=technique,
            level=3,
        )
        sheet.character.threads.invalidate()
        return technique, thread, bonus, condition, facet, resonance


# ---------------------------------------------------------------------------
# (c) + (d) + (e): selection-service journey — SQLite fast tier
# ---------------------------------------------------------------------------


class SignatureMotifE2ESelectionTests(_SignatureMotifE2EBase):
    """Service-layer selection journey: set / reject / clear / move (#1582).

    All tests run on the SQLite fast tier (no DISTINCT ON).
    """

    def test_set_signature_bonus_success(self):
        """set_signature_bonus returns the updated Thread when the bonus qualifies."""
        _technique, thread, bonus, _cond, _facet, _res = self._build_signature_fixture()

        updated = set_signature_bonus(thread, bonus)

        self.assertEqual(
            updated.signature_bonus_id,
            bonus.pk,
            "set_signature_bonus must attach the bonus to the thread.",
        )

    def test_non_qualifying_bonus_raises_not_available(self):
        """(c) A bonus whose required_facet is absent from the Motif is rejected."""
        _technique, thread, _bonus, _cond, _facet, _res = self._build_signature_fixture()

        # A bonus gated on a facet the character's Motif does NOT contain.
        other_facet = FacetFactory(name="E2E Unowned Facet")
        non_qualifying = SignatureMotifBonus.objects.create(
            name="E2E Non-Qualifying Bonus",
            required_facet=other_facet,
        )

        with self.assertRaises(SignatureBonusNotAvailable):
            set_signature_bonus(thread, non_qualifying)

    def test_technique_not_owned_raises_error(self):
        """(d) A TECHNIQUE thread for an unknown technique raises TechniqueNotOwned."""
        _technique, _thread, bonus, _cond, _facet, resonance = self._build_signature_fixture()
        sheet = self.caster.character_sheet

        # A technique the character has NOT been granted (no CharacterTechnique row).
        unowned_technique = make_benign_castable_technique()
        # Intentionally NO grant_technique() call here.

        unowned_thread = Thread.objects.create(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=unowned_technique,
            level=3,
        )
        sheet.character.threads.invalidate()

        # The bonus qualifies for the sheet (Motif has the required facet), but the
        # character does not own the technique → TechniqueNotOwned.
        with self.assertRaises(TechniqueNotOwned):
            set_signature_bonus(unowned_thread, bonus)

    def test_move_port_between_two_technique_threads(self):
        """(e) Move a bonus from thread A to thread B via clear → set (independent storage)."""
        _technique_a, thread_a, bonus, _cond, _facet, resonance = self._build_signature_fixture()
        sheet = self.caster.character_sheet

        # A second technique on the same sheet — same Motif/resonance/bonus qualifies.
        technique_b = make_benign_castable_technique()
        grant_technique(self.caster, technique_b)
        thread_b = Thread.objects.create(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=technique_b,
            level=3,
        )
        sheet.character.threads.invalidate()

        # --- Phase 1: set bonus on A → B still has no bonus ---
        set_signature_bonus(thread_a, bonus)
        thread_a.refresh_from_db()
        thread_b.refresh_from_db()
        self.assertEqual(thread_a.signature_bonus_id, bonus.pk)
        self.assertIsNone(thread_b.signature_bonus_id, "B must remain unsigned when A is signed.")

        # --- Phase 2: clear A (the "move" precondition) ---
        clear_signature_bonus(thread_a)
        thread_a.refresh_from_db()
        self.assertIsNone(thread_a.signature_bonus_id, "A must be cleared before the move.")

        # --- Phase 3: set bonus on B → A still has no bonus ---
        set_signature_bonus(thread_b, bonus)
        thread_a.refresh_from_db()
        thread_b.refresh_from_db()
        self.assertIsNone(
            thread_a.signature_bonus_id, "A must remain cleared after the bonus moves to B."
        )
        self.assertEqual(
            thread_b.signature_bonus_id, bonus.pk, "B must carry the bonus after move."
        )


# ---------------------------------------------------------------------------
# (a) + (b-intensity): cast narration + intensity delta — SQLite fast tier
# ---------------------------------------------------------------------------


class SignatureMotifE2ECastTests(_SignatureMotifE2EBase):
    """Cast-path journey: snippet in pose, intensity delta folds in — SQLite fast tier (#1582)."""

    def test_signed_cast_includes_narrative_snippet_in_outcome_pose(self):
        """(a) The cast outcome pose contains the bonus's narrative_snippet after signing."""
        technique, thread, bonus, _cond, _facet, _res = self._build_signature_fixture(
            narrative_snippet="silver threads shimmer through the strike",
            add_condition=False,
        )
        set_signature_bonus(thread, bonus)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            technique=technique,
        )

        self.assertIsNotNone(cast.outcome_interaction, "The cast must produce an outcome pose.")
        self.assertIn(
            "silver threads shimmer through the strike",
            cast.outcome_interaction.content,
            "The signed bonus's narrative_snippet must appear in the outcome pose.",
        )

    def test_unsigned_cast_has_no_signature_snippet_in_outcome_pose(self):
        """An unsigned cast does not include the signature snippet in the outcome pose."""
        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            technique=technique,
        )

        self.assertIsNotNone(cast.outcome_interaction)
        self.assertNotIn(
            "silver threads shimmer through the strike",
            cast.outcome_interaction.content,
            "An unsigned cast must not contain any signature snippet.",
        )

    def test_signed_cast_flat_intensity_delta_folds_into_power_intensity_bonus(self):
        """(b) The bonus's flat_intensity_delta is forwarded as power_intensity_bonus."""
        technique, thread, bonus, _cond, _facet, _res = self._build_signature_fixture(
            flat_intensity_delta=7,
            add_condition=False,
        )
        set_signature_bonus(thread, bonus)

        with patch("world.magic.services.use_technique") as mock_use:
            # Returning confirmed=False halts the cast before resolution — enough to
            # capture the call kwargs without needing a full resolution pipeline.
            mock_use.return_value = MagicMock(confirmed=False, resolution_result=None)
            request_technique_cast(
                scene=self.scene,
                initiator_persona=self.caster,
                technique=technique,
            )

        self.assertTrue(mock_use.called, "use_technique must be called during the cast.")
        self.assertEqual(
            mock_use.call_args.kwargs["power_intensity_bonus"],
            7,
            "The bonus's flat_intensity_delta must be forwarded as power_intensity_bonus=7.",
        )


# ---------------------------------------------------------------------------
# (b-condition): condition lands on cast — @tag("postgres")
# ---------------------------------------------------------------------------


@tag("postgres")
class SignatureMotifE2EConditionLandingTests(_SignatureMotifE2EBase):
    """(b) The signed bonus's applied condition lands on the caster after a successful cast.

    @tag("postgres"): get_active_conditions uses DISTINCT ON, which is PG-only.
    The 29 DISTINCT-ON failures in magic/vitals/mechanics (pre-existing) are unrelated.
    """

    @patch("world.scenes.cast_services.start_action_resolution")
    def test_signed_bonus_condition_lands_on_cast(self, mock_resolve):
        """The SELF-targeting condition row lands on the caster after a forced-success cast."""
        mock_resolve.return_value = _deterministic_success()

        technique, thread, bonus, condition, _facet, _res = self._build_signature_fixture()
        set_signature_bonus(thread, bonus)

        caster_obj = self.caster.character_sheet.character
        self.assertFalse(
            get_active_conditions(caster_obj, condition=condition).exists(),
            "Precondition: the caster must not carry the bonus condition before casting.",
        )

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            technique=technique,
        )

        self.assertIsNotNone(cast.outcome_interaction, "The cast must produce an outcome pose.")
        self.assertTrue(
            get_active_conditions(caster_obj, condition=condition).exists(),
            "The signature bonus's SELF condition must land on the caster after a successful cast.",
        )
