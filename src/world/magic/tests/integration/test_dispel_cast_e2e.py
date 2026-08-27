"""End-to-end dispel/cleanse journey (#1585).

A player casts a dispel technique that strips a condition from the resolved target.
This is the spec's primary acceptance gate (Postgres parity). Gate-logic is covered
by the SQLite-fast unit tests in ``world/magic/tests/test_condition_application.py``;
these journey tests assert the real cast path through ``request_technique_cast``
applies + removes conditions end-to-end.

Tagged ``postgres`` because the real apply/remove path routes through
``get_active_conditions`` which uses PG-only ``DISTINCT ON``.
"""

from decimal import Decimal
from types import SimpleNamespace

from django.test.utils import tag

from actions.factories import ActionTemplateFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.services import apply_condition, get_active_conditions
from world.magic.factories import (
    BinaryEffectTypeFactory,
    TechniqueFactory,
    TechniqueRemovedConditionFactory,
)
from world.magic.models.techniques import ConditionTargetKind
from world.scenes.cast_services import request_technique_cast
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    grant_technique,
    make_benign_castable_technique,
)


@tag("postgres")
class DispelCastE2ETests(CastScenarioMixin):
    """Journey: a dispel technique cast removes a condition end-to-end."""

    def _make_dispel_technique(self, *, condition, target_kind=ConditionTargetKind.SELF):
        """A benign castable technique carrying one removal (dispel) row.

        ``minimum_success_level=0`` so removal fires on any resolved cast — the cast
        check's real SL is non-deterministic in the test fixture (the per-character
        magic check botches ~half the time). The cast-SL gate behavior itself is
        unit-tested in test_condition_application.py::test_skips_row_below_minimum_sl;
        this E2E proves the plumbing (cast → remove_technique_conditions → condition
        gone), not the gate.
        """
        technique = make_benign_castable_technique()
        TechniqueRemovedConditionFactory(
            technique=technique,
            condition=condition,
            target_kind=target_kind,
            minimum_success_level=0,
            remove_all_stacks=True,
        )
        return technique

    def test_dispel_wiring_invokes_remove_on_cast(self):
        """The cast seam calls remove_technique_conditions for a dispel technique.

        Deterministic wiring proof: spy on the removal service (wrapping the real call)
        and assert it receives the dispel technique + the caster. Does not depend on the
        cast's non-deterministic check (which botches ~half the time in the SQLite
        fixture). The removal primitive's gate logic + actual deletion is unit-tested in
        test_condition_application.py.
        """
        from unittest.mock import patch

        from world.magic.services.condition_application import remove_technique_conditions
        from world.scenes import cast_services

        cond = ConditionTemplateFactory(name="DispelWiringE2E", can_be_dispelled=True)
        technique = self._make_dispel_technique(condition=cond)
        grant_technique(self.caster, technique)

        with patch.object(
            cast_services, "remove_technique_conditions", wraps=remove_technique_conditions
        ) as spy:
            cast = request_technique_cast(
                scene=self.scene,
                initiator_persona=self.caster,
                technique=technique,
            )
        spy.assert_called_once()
        self.assertIs(spy.call_args.kwargs["technique"], technique)
        self.assertIsNotNone(
            cast.outcome_interaction, "The cast should produce an outcome pose/log."
        )

    def test_dispel_leaves_non_dispellable_condition(self):
        """A condition with can_be_dispelled=False survives a dispel cast (no-op)."""
        cond = ConditionTemplateFactory(name="PlotLockedCurseE2E", can_be_dispelled=False)
        technique = self._make_dispel_technique(condition=cond)
        grant_technique(self.caster, technique)

        apply_condition(target=self.caster.character_sheet.character, condition=cond)
        self.assertTrue(
            get_active_conditions(self.caster.character_sheet.character, condition=cond).exists(),
        )

        request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            technique=technique,
        )

        # Non-dispellable: the condition persists.
        self.assertTrue(
            get_active_conditions(self.caster.character_sheet.character, condition=cond).exists(),
            "A non-dispellable condition must survive a dispel cast.",
        )

    def test_dispel_noop_when_condition_absent(self):
        """A dispel cast on a target without the condition is a no-op (cast still succeeds)."""
        cond = ConditionTemplateFactory(name="AbsentDispelE2E", can_be_dispelled=True)
        technique = self._make_dispel_technique(condition=cond)
        grant_technique(self.caster, technique)

        # No condition seeded.
        self.assertFalse(
            get_active_conditions(self.caster.character_sheet.character, condition=cond).exists(),
        )

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            technique=technique,
        )

        # Still absent, cast still resolved.
        self.assertFalse(
            get_active_conditions(self.caster.character_sheet.character, condition=cond).exists(),
        )
        self.assertIsNotNone(cast.outcome_interaction)

    def test_default_cure_power_multiplier_is_back_compat(self):
        """#3391 anchor test: cure_power_multiplier=0 (the field default) — a real
        cast, at any caster power (technique.intensity varied), behaves exactly like
        the pre-#3391 uncontested-dispel path: the condition is always removed.

        Uses a null cure_check_type (uncontested) so the outcome is deterministic
        regardless of the underlying dice roll — the back-compat bar is that power
        scaling introduces NO new variance when the multiplier is left at 0, which
        this proves across a matrix of eff_intensity values. The cast's OWN check
        (independent of the dispel gate) is forced to succeed so a botched cast roll
        (the SL<0 case, ~half the time in this fixture) can't be mistaken for a
        power-scaling regression.
        """
        from world.checks.test_helpers import force_check_outcome
        from world.traits.models import CheckOutcome

        success = CheckOutcome.objects.get(name="Success")
        cond = ConditionTemplateFactory(name="BackCompatDispel3391", can_be_dispelled=True)
        for intensity in (0, 10, 100):
            with self.subTest(intensity=intensity):
                technique = TechniqueFactory(
                    effect_type=BinaryEffectTypeFactory(),
                    damage_profile=False,
                    action_template=ActionTemplateFactory(),
                    intensity=max(intensity, 1),
                )
                TechniqueRemovedConditionFactory(
                    technique=technique,
                    condition=cond,
                    target_kind=ConditionTargetKind.SELF,
                    minimum_success_level=0,
                    remove_all_stacks=True,
                    # cure_power_multiplier left at the field default (0).
                )
                grant_technique(self.caster, technique)
                apply_condition(target=self.caster.character_sheet.character, condition=cond)

                with force_check_outcome(success):
                    request_technique_cast(
                        scene=self.scene,
                        initiator_persona=self.caster,
                        technique=technique,
                    )

                self.assertFalse(
                    get_active_conditions(
                        self.caster.character_sheet.character, condition=cond
                    ).exists(),
                    "cure_power_multiplier=0 must behave like pre-#3391 (uncontested "
                    "dispel always removes), regardless of eff_intensity.",
                )

    def test_higher_power_dispels_more_reliably(self):
        """#3391 journey: a nonzero cure_power_multiplier makes a higher-power caster's
        dispel succeed against a contested cure check where a lower-power caster's
        does not — provably different outcomes from power alone, same condition, same
        multiplier, same cure_difficulty.

        The cast's OWN check is forced to succeed (``force_check_outcome``) so the row's
        SL gate always passes deterministically. The cure check itself is a scoped patch
        (isolated to ``world.magic.services.condition_application``, so it never
        intercepts the cast's own, separate check call) whose *outcome* is derived from
        the real ``extra_modifiers`` the production code computed and passed in —
        proving genuine wiring (a real, non-hardcoded power_bonus value determines the
        result) without relying on real dice variance, which flaked under concurrent
        test-suite load.
        """
        from unittest.mock import patch

        from world.checks.test_helpers import force_check_outcome
        from world.traits.models import CheckOutcome

        success = CheckOutcome.objects.get(name="Success")
        failure = CheckOutcome.objects.filter(success_level__lt=0).first()
        assert failure is not None, "fixture needs a failure-tier CheckOutcome"
        cure_check = CheckTypeFactory()
        cond = ConditionTemplateFactory(
            name="PowerJourneyDispel3391",
            can_be_dispelled=True,
            cure_check_type=cure_check,
            cure_difficulty=40,
        )

        def _make_dispel_technique(intensity: int):
            technique = TechniqueFactory(
                effect_type=BinaryEffectTypeFactory(),
                damage_profile=False,
                action_template=ActionTemplateFactory(),
                intensity=intensity,
            )
            TechniqueRemovedConditionFactory(
                technique=technique,
                condition=cond,
                target_kind=ConditionTargetKind.SELF,
                minimum_success_level=0,
                remove_all_stacks=True,
                cure_power_multiplier=Decimal(5),
            )
            grant_technique(self.caster, technique)
            return technique

        low_technique = _make_dispel_technique(intensity=1)
        high_technique = _make_dispel_technique(intensity=500)

        def _fake_cure_check(*args, extra_modifiers=0, **kwargs):
            # A real power_bonus of int(5 * 1)=5 (low caster) stays under the bar;
            # int(5 * 500)=2500 (high caster) clears it. The outcome genuinely
            # reflects what the production code computed and passed in.
            outcome = success if extra_modifiers >= 100 else failure
            return SimpleNamespace(outcome=outcome, success_level=outcome.success_level)

        def _trial(technique) -> bool:
            apply_condition(target=self.caster.character_sheet.character, condition=cond)
            with (
                patch(
                    "world.magic.services.condition_application.perform_check_with_modifiers",
                    side_effect=_fake_cure_check,
                ),
                force_check_outcome(success),
            ):
                request_technique_cast(
                    scene=self.scene,
                    initiator_persona=self.caster,
                    technique=technique,
                )
            return not get_active_conditions(
                self.caster.character_sheet.character, condition=cond
            ).exists()

        self.assertFalse(_trial(low_technique), "low-power caster's dispel should be resisted")
        self.assertTrue(_trial(high_technique), "high-power caster's dispel should succeed")
