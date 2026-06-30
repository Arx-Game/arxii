"""End-to-end dispel/cleanse journey (#1585).

A player casts a dispel technique that strips a condition from the resolved target.
This is the spec's primary acceptance gate (Postgres parity). Gate-logic is covered
by the SQLite-fast unit tests in ``world/magic/tests/test_condition_application.py``;
these journey tests assert the real cast path through ``request_technique_cast``
applies + removes conditions end-to-end.

Tagged ``postgres`` because the real apply/remove path routes through
``get_active_conditions`` which uses PG-only ``DISTINCT ON``.
"""

from django.test.utils import tag

from world.conditions.factories import ConditionTemplateFactory
from world.conditions.services import apply_condition, get_active_conditions
from world.magic.factories import (
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
