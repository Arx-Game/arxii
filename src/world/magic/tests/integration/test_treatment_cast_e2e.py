"""End-to-end technique-treatment cast power journey (#3391).

A player casts a bounded-mend treatment technique whose power (effective intensity)
scales the mend amount, routed through the real ``request_technique_cast`` seam.
Wiring/gate-level unit coverage lives in ``world/magic/tests/test_technique_treatment.py``
and ``world/conditions/tests/test_wound_treatment.py``; this journey test proves the
real cast path measurably heals a higher-power caster more than a lower-power one.

Two independent dice rolls sit on the path between "cast" and "mend": the cast's own
check (gates whether ``apply_technique_treatments`` runs its row's SL gate at all) and
the treatment's own internal check (gates the mend outcome tier). Both are made
deterministic here — the cast's own check via the shared ``force_check_outcome``
test-rig seam (``world/checks/test_helpers.py``), the treatment's own check via a
scoped patch of ``world.conditions.services.perform_check_with_modifiers`` (isolated to
that one call site so it doesn't also intercept the cast's own, separate check call).
This keeps the journey deterministic while leaving the actual eff_intensity plumbing
and ``mend_wound()`` cap math genuinely exercised, unmocked.

Tagged ``postgres`` — the standalone cast pipeline this rides shares machinery with the
dispel/apply journeys (``world/magic/tests/integration/test_dispel_cast_e2e.py``), which
require PG-only ``DISTINCT ON``.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test.utils import tag

from actions.factories import ActionTemplateFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.constants import TreatmentTargetKind
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    TreatmentTemplateFactory,
)
from world.magic.factories import BinaryEffectTypeFactory, TechniqueFactory
from world.magic.models.techniques import ConditionTargetKind, TechniqueTreatment
from world.scenes.cast_services import request_technique_cast
from world.scenes.tests.cast_test_helpers import CastScenarioMixin, grant_technique
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals, WoundDetails


class _FixedCheckResult:
    """Minimal stand-in for a ``CheckResult`` — just what ``perform_treatment`` reads."""

    def __init__(self, outcome: CheckOutcome) -> None:
        self.outcome = outcome
        self.success_level = outcome.success_level


@tag("postgres")
class TreatmentPowerJourneyE2ETests(CastScenarioMixin):
    """Journey: a technique-treatment cast heals more for a higher-power caster."""

    def setUp(self) -> None:
        super().setUp()
        # Plenty of headroom under both mend_wound() bounds (fraction cap +
        # max_health clamp) so the power difference isn't cap-masked.
        self._set_vitals(health=10, max_health=1_000_000)
        self.cast_success = CheckOutcome.objects.get(name="Success")
        self.treatment_check_result = _FixedCheckResult(self.cast_success)

    def _set_vitals(self, *, health: int, max_health: int) -> None:
        """Set the caster's vitals so the cast pipeline actually sees them.

        Django's ``TestCase.setUpTestData`` mechanism hands ``self.caster`` back
        as a per-test deep copy — a Python object disconnected from idmapper's
        identity map. Mutating ``self.caster.character_sheet.vitals`` therefore
        never reaches the *real*, globally-cached ``CharacterSheet`` the cast
        pipeline resolves via fresh queries (``CharacterSheet.objects.get(character=
        ...)``); that real instance's cached ``.vitals`` reverse-O2O accessor was
        populated once, at class-level ``setUpTestData``, and Django's per-instance
        ``_state.fields_cache`` is a separate cache from idmapper's own — flushing
        the latter doesn't touch it. Fix: resolve the real, non-deep-copied sheet by
        pk, update the DB, and explicitly evict its cached reverse relation.
        """
        from world.character_sheets.models import CharacterSheet

        real_sheet = CharacterSheet.objects.get(pk=self.caster.character_sheet.pk)
        CharacterVitals.objects.filter(character_sheet=real_sheet).update(
            health=health, max_health=max_health
        )
        CharacterVitals.flush_instance_cache()
        real_sheet._state.fields_cache.pop("vitals", None)

    def _make_wound(self, *, treatment_template, damage_taken: int = 1000):
        """Create a fresh wound (condition template + instance) and repoint
        *treatment_template* at it.

        A fresh template per call is required: ``ConditionInstance`` is unique per
        ``(target, condition)``, and this suite's treatments carry no severity
        reduction, so a prior unresolved wound on the same template would block a
        second instance outright.
        """
        # No explicit name: ConditionTemplateFactory keys django_get_or_create on
        # name, so a colliding name here would silently reuse an existing row
        # (id(object()) on a throwaway temporary can repeat within a process) —
        # let the factory's own Sequence guarantee uniqueness instead.
        condition = ConditionTemplateFactory()
        treatment_template.target_condition = condition
        treatment_template.save(update_fields=["target_condition"])
        wound = ConditionInstanceFactory(
            target=self.caster.character_sheet.character,
            condition=condition,
            severity=1,
        )
        WoundDetails.objects.create(condition_instance=wound, damage_taken=damage_taken)
        return wound

    def _make_treatment_technique(self, *, intensity: int, treatment_template):
        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(),
            intensity=intensity,
        )
        TechniqueTreatment.objects.create(
            technique=technique,
            treatment_template=treatment_template,
            target_kind=ConditionTargetKind.SELF,
            minimum_success_level=0,
        )
        grant_technique(self.caster, technique)
        return technique

    def _refresh_health(self) -> int:
        # A fresh queryset read, not the (possibly idmapper-stale) cached instance —
        # see the note in setUp() about CharacterVitals identity-map staleness.
        return CharacterVitals.objects.get(character_sheet=self.caster.character_sheet).health

    def _cast_with_deterministic_checks(self, technique) -> None:
        """Cast *technique*, forcing BOTH dice rolls on the path to a deterministic
        success — the cast's own check (via the shared force-outcome test rig) and
        the treatment's own internal check (via a scoped patch isolated to
        ``world.conditions.services``, so it never intercepts the cast's own,
        separate check call).
        """
        with (
            patch(
                "world.conditions.services.perform_check_with_modifiers",
                return_value=self.treatment_check_result,
            ),
            force_check_outcome(self.cast_success),
        ):
            request_technique_cast(
                scene=self.scene,
                initiator_persona=self.caster,
                technique=technique,
            )

    def test_higher_power_heals_more(self):
        """#3391 journey: mend_intensity_multiplier > 0 makes a higher-power caster's
        treatment mend more than a lower-power caster's — same treatment template, same
        wound shape, only technique.intensity (and therefore eff_intensity) differs.
        """
        wound_template = ConditionTemplateFactory(name="TreatmentPowerJourneyWound3391")
        treatment_template = TreatmentTemplateFactory(
            target_kind=TreatmentTargetKind.PRIMARY,
            target_condition=wound_template,
            check_type=CheckTypeFactory(),
            target_difficulty=0,
            requires_bond=False,
            scene_required=False,
            once_per_scene_per_helper=False,
            once_per_wound_per_helper=True,
            mend_on_crit=20,
            mend_on_success=10,
            mend_on_partial=5,
            mend_intensity_multiplier=Decimal(5),
        )
        low_technique = self._make_treatment_technique(
            intensity=1, treatment_template=treatment_template
        )
        high_technique = self._make_treatment_technique(
            intensity=200, treatment_template=treatment_template
        )

        start_health = self._refresh_health()
        self._make_wound(treatment_template=treatment_template)
        self._cast_with_deterministic_checks(low_technique)
        after_low_health = self._refresh_health()
        low_mended = after_low_health - start_health

        self._make_wound(treatment_template=treatment_template)
        self._cast_with_deterministic_checks(high_technique)
        after_high_health = self._refresh_health()
        high_mended = after_high_health - after_low_health

        self.assertGreater(
            high_mended,
            low_mended,
            f"high-power caster should heal more than low-power "
            f"(low={low_mended}, high={high_mended})",
        )

    def test_power_still_capped_by_never_to_full_fraction(self):
        """A single overwhelming-power cast still gets clamped by mend_wound()'s
        never-to-full fraction cap (ADR-0156, Decision 3) — power composes with the
        double-bound, it does not bypass it.
        """
        wound_template = ConditionTemplateFactory(name="TreatmentPowerCapJourney3391")
        treatment_template = TreatmentTemplateFactory(
            target_kind=TreatmentTargetKind.PRIMARY,
            target_condition=wound_template,
            check_type=CheckTypeFactory(),
            target_difficulty=0,
            requires_bond=False,
            scene_required=False,
            once_per_scene_per_helper=False,
            once_per_wound_per_helper=True,
            mend_on_crit=20,
            mend_on_success=10,
            mend_on_partial=5,
            mend_intensity_multiplier=Decimal(50),
        )
        # damage_taken=100 -> fraction cap = floor(0.75 * 100) = 75. A power
        # contribution of floor(50 * 1000) = 50000 overwhelms it many times over.
        technique = self._make_treatment_technique(
            intensity=1000, treatment_template=treatment_template
        )
        self._make_wound(treatment_template=treatment_template, damage_taken=100)
        start_health = self._refresh_health()

        self._cast_with_deterministic_checks(technique)

        mended = self._refresh_health() - start_health
        self.assertEqual(
            mended, 75, "mend must be clamped exactly at the never-to-full fraction cap"
        )
