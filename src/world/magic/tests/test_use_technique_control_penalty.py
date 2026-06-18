"""Tests for use_technique control_penalty parameter (#567)."""

from types import SimpleNamespace

from django.test import TestCase

from world.magic.factories import (
    CharacterAnimaFactory,
    TechniqueFactory,
)
from world.magic.services import use_technique
from world.magic.services.techniques import calculate_effective_anima_cost
from world.mechanics.factories import CharacterEngagementFactory


def _noop_resolve(*, power: int, ledger: object = None) -> SimpleNamespace:
    return SimpleNamespace(check_result=None)


# ---------------------------------------------------------------------------
# Direction test: calculate_effective_anima_cost responds to control delta
# ---------------------------------------------------------------------------


class EffectiveAnimaCostDirectionTests(TestCase):
    """Direction test: lower runtime_control raises effective anima cost."""

    def test_lower_control_raises_effective_cost(self) -> None:
        """Lower runtime_control → higher effective anima cost."""
        base = calculate_effective_anima_cost(
            base_cost=10,
            runtime_intensity=5,
            runtime_control=8,
            current_anima=100,
        )
        penalised = calculate_effective_anima_cost(
            base_cost=10,
            runtime_intensity=5,
            runtime_control=8 - 4,
            current_anima=100,
        )
        self.assertGreater(penalised.effective_cost, base.effective_cost)


# ---------------------------------------------------------------------------
# Behavioural integration test: control_penalty flows through use_technique
# ---------------------------------------------------------------------------


class ControlPenaltyIntegrationTests(TestCase):
    """control_penalty lowers the runtime control reaching cost and mishap paths."""

    @classmethod
    def setUpTestData(cls) -> None:
        # control=20, intensity=5 → big control surplus → low baseline cost.
        # Applying a penalty eats into that surplus and raises effective cost.
        cls.technique = TechniqueFactory(intensity=5, control=20, anima_cost=10)

    def _make_caster(self) -> object:
        anima = CharacterAnimaFactory(current=50, maximum=50)
        character = anima.character
        CharacterEngagementFactory(character=character)
        return character, anima

    def test_control_penalty_raises_effective_anima_cost(self) -> None:
        """use_technique(..., control_penalty=N) deducts more anima than the baseline cast."""
        # Baseline cast — no penalty
        baseline_char, baseline_anima = self._make_caster()
        use_technique(
            character=baseline_char,
            technique=self.technique,
            resolve_fn=_noop_resolve,
        )
        baseline_anima.refresh_from_db()
        baseline_deducted = 50 - baseline_anima.current

        # Penalised cast — control_penalty lowers runtime control → larger cost
        penalty_char, penalty_anima = self._make_caster()
        use_technique(
            character=penalty_char,
            technique=self.technique,
            resolve_fn=_noop_resolve,
            control_penalty=10,
        )
        penalty_anima.refresh_from_db()
        penalised_deducted = 50 - penalty_anima.current

        self.assertGreater(
            penalised_deducted,
            baseline_deducted,
            msg=(
                f"control_penalty=10 should raise effective anima cost above baseline "
                f"({penalised_deducted} should be > {baseline_deducted})"
            ),
        )

    def test_zero_control_penalty_is_identical_to_no_penalty(self) -> None:
        """control_penalty=0 (the default) must not change the effective cost."""
        baseline_char, baseline_anima = self._make_caster()
        use_technique(
            character=baseline_char,
            technique=self.technique,
            resolve_fn=_noop_resolve,
        )
        baseline_anima.refresh_from_db()
        baseline_deducted = 50 - baseline_anima.current

        zero_char, zero_anima = self._make_caster()
        use_technique(
            character=zero_char,
            technique=self.technique,
            resolve_fn=_noop_resolve,
            control_penalty=0,
        )
        zero_anima.refresh_from_db()
        zero_deducted = 50 - zero_anima.current

        self.assertEqual(
            zero_deducted,
            baseline_deducted,
            msg="control_penalty=0 should be identical to the default (no param)",
        )

    def test_control_penalty_clamped_to_zero_floor(self) -> None:
        """A penalty larger than runtime control must not produce a negative control value."""
        # Technique with very low base control; a huge penalty should not crash.
        technique = TechniqueFactory(intensity=5, control=2, anima_cost=5)
        caster, anima = self._make_caster()
        # Should not raise; control clamped to 0, not negative.
        use_technique(
            character=caster,
            technique=technique,
            resolve_fn=_noop_resolve,
            control_penalty=999,
        )
        anima.refresh_from_db()
        # We just assert it completed without error; any deduction is valid.
        self.assertGreaterEqual(anima.current, 0)
