"""Tests for world.magic.narration — shared power-ledger narration helpers.

Covers:
- power_outcome_clause: pure unit tests over constructed PowerLedgers.
- render_cast_outcome_narration: deterministic one-line scene-cast narration.
"""

from django.test import SimpleTestCase

from world.magic.constants import PowerStage
from world.magic.narration import power_outcome_clause, render_cast_outcome_narration
from world.magic.types.power_ledger import PowerLedger, PowerLedgerBuilder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_ledger(power: int = 100) -> PowerLedger:
    """Plain base-only ledger — no ward or environment stages."""
    return PowerLedgerBuilder(base=power).build()


def _bounce_ledger() -> PowerLedger:
    """Full bounce: PENETRATION SET 0, label 'ward (bounced)'."""
    return (
        PowerLedgerBuilder(base=100).set_value(PowerStage.PENETRATION, "ward (bounced)", 0).build()
    )


def _partial_ledger() -> PowerLedger:
    """Partial bleed: PENETRATION MULTIPLY -50 pct (ward reduces power by half)."""
    return PowerLedgerBuilder(base=100).multiply(PowerStage.PENETRATION, "ward", -50).build()


def _clean_penetration_ledger() -> PowerLedger:
    """Clean penetration: PENETRATION SET to current total, label 'ward (penetrated)'."""
    return (
        PowerLedgerBuilder(base=100)
        .set_value(PowerStage.PENETRATION, "ward (penetrated)", 100)
        .build()
    )


def _overpenetration_ledger() -> PowerLedger:
    """Overpenetration: PENETRATION MULTIPLY positive pct (ward amplifies the working)."""
    return PowerLedgerBuilder(base=100).multiply(PowerStage.PENETRATION, "ward", 20).build()


def _environment_ledger() -> PowerLedger:
    """Environment amplification: ENVIRONMENT ADD positive."""
    return (
        PowerLedgerBuilder(base=100)
        .add(PowerStage.ENVIRONMENT, "resonance environment", 30)
        .build()
    )


# ---------------------------------------------------------------------------
# power_outcome_clause unit tests
# ---------------------------------------------------------------------------


class PowerOutcomeClauseTest(SimpleTestCase):
    def test_none_ledger_returns_empty(self) -> None:
        assert power_outcome_clause(None) == ""

    def test_base_only_ledger_returns_empty(self) -> None:
        """A ledger with only a BASE stage produces no dramatic clause."""
        assert power_outcome_clause(_base_ledger()) == ""

    def test_bounce_returns_ward_turns_aside(self) -> None:
        clause = power_outcome_clause(_bounce_ledger())
        assert "ward" in clause
        assert "turns it aside" in clause

    def test_partial_returns_bleeds_off(self) -> None:
        clause = power_outcome_clause(_partial_ledger())
        assert "ward" in clause
        assert "bleed" in clause

    def test_clean_penetration_returns_tears_through(self) -> None:
        clause = power_outcome_clause(_clean_penetration_ledger())
        assert "tears through" in clause
        assert "ward" in clause

    def test_overpenetration_returns_tears_through(self) -> None:
        """Positive PENETRATION MULTIPLY (factor > 1) also resolves as tears-through."""
        clause = power_outcome_clause(_overpenetration_ledger())
        assert "tears through" in clause
        assert "ward" in clause

    def test_environment_add_returns_resonance_clause(self) -> None:
        clause = power_outcome_clause(_environment_ledger())
        assert "resonance" in clause or "place" in clause

    def test_bounce_priority_over_environment(self) -> None:
        """When both bounce and environment are present, bounce wins."""
        ledger = (
            PowerLedgerBuilder(base=100)
            .add(PowerStage.ENVIRONMENT, "resonance environment", 30)
            .set_value(PowerStage.PENETRATION, "ward (bounced)", 0)
            .build()
        )
        clause = power_outcome_clause(ledger)
        assert "turns it aside" in clause

    def test_partial_priority_over_environment(self) -> None:
        """When both partial penetration and environment amplification are present,
        penetration wins."""
        ledger = (
            PowerLedgerBuilder(base=100)
            .add(PowerStage.ENVIRONMENT, "resonance environment", 30)
            .multiply(PowerStage.PENETRATION, "ward", -40)
            .build()
        )
        clause = power_outcome_clause(ledger)
        assert "bleed" in clause

    def test_environment_negative_add_not_surfaced(self) -> None:
        """A negative ENVIRONMENT ADD (hostile environment) produces no clause."""
        ledger = (
            PowerLedgerBuilder(base=100)
            .add(PowerStage.ENVIRONMENT, "resonance environment", -20)
            .build()
        )
        assert power_outcome_clause(ledger) == ""


# ---------------------------------------------------------------------------
# render_cast_outcome_narration unit tests
# ---------------------------------------------------------------------------


class RenderCastOutcomeNarrationTest(SimpleTestCase):
    def test_self_no_target_no_ledger(self) -> None:
        """Self/no-target cast with no ledger: plain outcome sentence."""
        result = render_cast_outcome_narration(
            actor_label="Kira",
            technique_name="Inner Light",
            target_label=None,
            outcome_label="Decisive Success",
            success_level=2,
            power_ledger=None,
        )
        assert result == "Kira casts Inner Light: Decisive Success."

    def test_targeted_with_bounce_ledger(self) -> None:
        """Targeted cast with a bounce ledger appends the ward clause."""
        ledger = (
            PowerLedgerBuilder(base=100)
            .set_value(PowerStage.PENETRATION, "ward (bounced)", 0)
            .build()
        )
        result = render_cast_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="Davos",
            outcome_label="Failure",
            success_level=0,
            power_ledger=ledger,
        )
        assert result == "Kira casts Frost Bolt at Davos: Failure — the ward turns it aside."

    def test_targeted_no_ledger(self) -> None:
        """Targeted cast with no ledger: plain outcome sentence with target."""
        result = render_cast_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="Davos",
            outcome_label="Success",
            success_level=1,
            power_ledger=None,
        )
        assert result == "Kira casts Frost Bolt at Davos: Success."
