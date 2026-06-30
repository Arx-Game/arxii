"""End-to-end signature-bonus cast journey (#1582, Task 5).

A character signs a technique (their active TECHNIQUE-kind Thread carries a
``SignatureMotifBonus``).  When they cast that technique, the bonus's effect
payload applies on top of the technique's own payload:

- the bonus's ``SignatureMotifBonusAppliedCondition`` lands on the resolved
  target through the SAME ``apply_technique_conditions`` seam the technique's
  own conditions use (no parallel apply path);
- the bonus's ``flat_intensity_delta`` folds into the resolved cast intensity
  via ``use_technique(power_intensity_bonus=...)``.

The landing test forces a deterministic successful resolution (the per-character
magic check otherwise botches ~half the time — see ``test_dispel_cast_e2e``). It
is ``@tag("postgres")`` because the real apply path routes through
``get_active_conditions`` (PG-only ``DISTINCT ON``). The no-op and intensity-fold
tests are deterministic and run on the SQLite fast tier.
"""

from unittest.mock import MagicMock, patch

from django.test.utils import tag

from actions.constants import ResolutionPhase
from actions.types import PendingActionResolution, StepResult
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.services import get_active_conditions
from world.magic.constants import TargetKind
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
from world.scenes.cast_services import request_technique_cast
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    grant_technique,
    make_benign_castable_technique,
)


def _make_success_resolution() -> PendingActionResolution:
    """A resolved PendingActionResolution with success_level=1 (deterministic cast)."""
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


class SignatureCastMixin(CastScenarioMixin):
    """Fixture helper: grant + sign a benign castable technique on the caster."""

    def _sign_technique(
        self,
        *,
        condition=None,
        target_kind=ConditionTargetKind.SELF,
        flat_intensity_delta=0,
        narrative_snippet="",
    ):
        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)
        sheet = self.caster.character_sheet

        # Motif gate: a facet bound to the motif so ``bonus.qualifies_for`` passes.
        motif = MotifFactory(character=sheet)
        resonance = ResonanceFactory()
        facet = FacetFactory(name="Sig Cast Facet")
        motif_res = MotifResonanceFactory(motif=motif, resonance=resonance)
        MotifResonanceAssociationFactory(motif_resonance=motif_res, facet=facet)

        bonus = SignatureMotifBonus.objects.create(
            name="Signed Strike",
            required_facet=facet,
            flat_intensity_delta=flat_intensity_delta,
            narrative_snippet=narrative_snippet,
        )
        if condition is not None:
            SignatureMotifBonusAppliedCondition.objects.create(
                signature_bonus=bonus,
                condition=condition,
                target_kind=target_kind,
                minimum_success_level=0,
                base_severity=1,
                stack_count=1,
            )

        Thread.objects.create(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=technique,
            signature_bonus=bonus,
        )
        sheet.character.threads.invalidate()
        return technique, bonus


@tag("postgres")
class SignatureCastConditionLandingTests(SignatureCastMixin):
    """The signed technique's bonus condition lands on the resolved target."""

    @patch("world.scenes.cast_services.start_action_resolution")
    def test_signature_bonus_condition_lands_on_cast(self, mock_resolve):
        mock_resolve.return_value = _make_success_resolution()
        cond = ConditionTemplateFactory(name="SignatureMarkE2E", can_be_dispelled=True)
        technique, _bonus = self._sign_technique(condition=cond)

        caster_obj = self.caster.character_sheet.character
        self.assertFalse(get_active_conditions(caster_obj, condition=cond).exists())

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            technique=technique,
        )

        self.assertIsNotNone(cast.outcome_interaction, "The cast should produce an outcome pose.")
        self.assertTrue(
            get_active_conditions(caster_obj, condition=cond).exists(),
            "The signature bonus's condition must land on the caster (SELF target).",
        )


class SignatureCastFastTests(SignatureCastMixin):
    """Deterministic, SQLite-fast-tier coverage (no real condition apply)."""

    def test_unsigned_technique_applies_no_signature_condition(self):
        """A technique with no signature bonus is a no-op for signature effects."""
        cond = ConditionTemplateFactory(name="UnsignedNoMarkE2E", can_be_dispelled=True)
        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            technique=technique,
        )

        self.assertIsNotNone(cast.outcome_interaction)
        self.assertFalse(
            get_active_conditions(self.caster.character_sheet.character, condition=cond).exists(),
            "An unsigned cast must not apply any signature condition.",
        )

    def test_flat_intensity_delta_folds_into_power_bonus(self):
        """The bonus's flat_intensity_delta is added to use_technique's power_intensity_bonus."""
        technique, _bonus = self._sign_technique(condition=None, flat_intensity_delta=7)

        with patch("world.magic.services.use_technique") as mock_use:
            # use_technique returning unconfirmed halts before resolution — enough to
            # capture the call kwargs without needing a full resolution.
            mock_use.return_value = MagicMock(confirmed=False, resolution_result=None)
            request_technique_cast(
                scene=self.scene,
                initiator_persona=self.caster,
                technique=technique,
            )

        self.assertTrue(mock_use.called)
        self.assertEqual(mock_use.call_args.kwargs["power_intensity_bonus"], 7)


class SignatureCastNarrationTests(SignatureCastMixin):
    """Cosmetic signature narration on the cast outcome pose (SQLite-fast, deterministic)."""

    def test_signed_technique_narration_contains_snippet(self):
        """The cast outcome pose text contains the bonus's narrative_snippet."""
        technique, _bonus = self._sign_technique(
            narrative_snippet="spectral webs shimmer through the air"
        )
        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            technique=technique,
        )
        self.assertIsNotNone(cast.outcome_interaction)
        self.assertIn(
            "spectral webs shimmer through the air",
            cast.outcome_interaction.content,
            "The outcome pose must contain the bonus's narrative_snippet.",
        )

    def test_signed_technique_narration_fallback_facet_name(self):
        """When narrative_snippet is blank the outcome pose contains the primary facet name."""
        technique, _bonus = self._sign_technique(narrative_snippet="")
        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            technique=technique,
        )
        self.assertIsNotNone(cast.outcome_interaction)
        self.assertIn(
            "Sig Cast Facet",
            cast.outcome_interaction.content,
            "When narrative_snippet is blank the facet name must appear in the pose.",
        )

    def test_unsigned_technique_has_no_signature_snippet_in_pose(self):
        """An unsigned cast does not contain any signature snippet in the outcome pose."""
        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)
        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            technique=technique,
        )
        self.assertIsNotNone(cast.outcome_interaction)
        # Neither the well-known snippet text nor the facet name used by _sign_technique
        # should appear in the pose for an unsigned technique.
        self.assertNotIn("spectral webs shimmer", cast.outcome_interaction.content)
        self.assertNotIn("Sig Cast Facet", cast.outcome_interaction.content)
