"""Tests for power-ledger-driven outcome narration clauses.

Covers:
- _power_outcome_clause: pure unit tests over constructed PowerLedgers.
- render_action_outcome_narration: back-compat (power_ledger=None) and
  clause-integration (bounce ledger appends clause; no-ledger does not).
"""

from django.test import SimpleTestCase

from world.combat.interaction_services import render_action_outcome_narration
from world.combat.types import ActionOutcome, OpponentDamageResult
from world.magic.constants import PowerStage
from world.magic.narration import power_outcome_clause as _power_outcome_clause
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


def _opp_dmg(*, damage_dealt: int, defeated: bool = False) -> OpponentDamageResult:
    return OpponentDamageResult(
        damage_dealt=damage_dealt,
        health_damaged=damage_dealt > 0,
        probed=False,
        probing_increment=0,
        defeated=defeated,
    )


# ---------------------------------------------------------------------------
# _power_outcome_clause unit tests
# ---------------------------------------------------------------------------


class PowerOutcomeClauseTest(SimpleTestCase):
    def test_none_ledger_returns_empty(self) -> None:
        assert _power_outcome_clause(None) == ""

    def test_base_only_ledger_returns_empty(self) -> None:
        """A ledger with only a BASE stage produces no dramatic clause."""
        assert _power_outcome_clause(_base_ledger()) == ""

    def test_bounce_returns_ward_turns_aside(self) -> None:
        clause = _power_outcome_clause(_bounce_ledger())
        assert "ward" in clause
        assert "turns it aside" in clause

    def test_partial_returns_bleeds_off(self) -> None:
        clause = _power_outcome_clause(_partial_ledger())
        assert "ward" in clause
        assert "bleed" in clause

    def test_clean_penetration_returns_tears_through(self) -> None:
        clause = _power_outcome_clause(_clean_penetration_ledger())
        assert "tears through" in clause
        assert "ward" in clause

    def test_overpenetration_returns_tears_through(self) -> None:
        """Positive PENETRATION MULTIPLY (factor > 1) also resolves as tears-through."""
        clause = _power_outcome_clause(_overpenetration_ledger())
        assert "tears through" in clause
        assert "ward" in clause

    def test_environment_add_returns_resonance_clause(self) -> None:
        clause = _power_outcome_clause(_environment_ledger())
        assert "resonance" in clause or "place" in clause

    def test_bounce_priority_over_environment(self) -> None:
        """When both bounce and environment are present, bounce wins."""
        ledger = (
            PowerLedgerBuilder(base=100)
            .add(PowerStage.ENVIRONMENT, "resonance environment", 30)
            .set_value(PowerStage.PENETRATION, "ward (bounced)", 0)
            .build()
        )
        clause = _power_outcome_clause(ledger)
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
        clause = _power_outcome_clause(ledger)
        assert "bleed" in clause

    def test_environment_negative_add_not_surfaced(self) -> None:
        """A negative ENVIRONMENT ADD (hostile environment) produces no clause."""
        ledger = (
            PowerLedgerBuilder(base=100)
            .add(PowerStage.ENVIRONMENT, "resonance environment", -20)
            .build()
        )
        assert _power_outcome_clause(ledger) == ""


# ---------------------------------------------------------------------------
# render_action_outcome_narration + power_ledger integration
# ---------------------------------------------------------------------------


class RenderOutcomeNarrationWithLedgerTest(SimpleTestCase):
    def _outcome_with_damage(self, damage: int = 30) -> ActionOutcome:
        outcome = ActionOutcome(entity_type="pc", entity_label="Kira")
        outcome.damage_results.append(_opp_dmg(damage_dealt=damage))
        return outcome

    def _miss_outcome(self) -> ActionOutcome:
        outcome = ActionOutcome(entity_type="pc", entity_label="Kira")
        outcome.damage_results.append(_opp_dmg(damage_dealt=0))
        return outcome

    def test_no_ledger_backward_compat_hit(self) -> None:
        """power_ledger=None → no extra clause (existing callers unchanged)."""
        text = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="the Pyromancer",
            outcome=self._outcome_with_damage(24),
            power_ledger=None,
        )
        assert "Kira" in text
        assert "24" in text
        assert "ward" not in text
        assert "resonance" not in text

    def test_no_ledger_backward_compat_miss(self) -> None:
        """power_ledger=None → plain miss, no clause."""
        text = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="the Pyromancer",
            outcome=self._miss_outcome(),
            power_ledger=None,
        )
        assert "miss" in text.lower()
        assert "ward" not in text

    def test_bounce_ledger_appends_clause_on_miss(self) -> None:
        """A bounce ledger folds a ward clause into the miss line."""
        text = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="the Pyromancer",
            outcome=self._miss_outcome(),
            power_ledger=_bounce_ledger(),
        )
        assert "miss" in text.lower()
        assert "ward" in text
        assert "turns it aside" in text

    def test_environment_ledger_appends_clause_on_hit(self) -> None:
        """An environment amplification clause is folded into the hit line."""
        text = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="the Pyromancer",
            outcome=self._outcome_with_damage(30),
            power_ledger=_environment_ledger(),
        )
        assert "resonance" in text or "place" in text

    def test_clean_penetration_appends_tears_through_on_hit(self) -> None:
        text = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="the Pyromancer",
            outcome=self._outcome_with_damage(30),
            power_ledger=_clean_penetration_ledger(),
        )
        assert "tears through" in text
        assert "ward" in text

    def test_partial_ledger_appends_bleed_clause_on_hit(self) -> None:
        text = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="the Pyromancer",
            outcome=self._outcome_with_damage(15),
            power_ledger=_partial_ledger(),
        )
        assert "bleed" in text
        assert "ward" in text

    def test_base_only_ledger_no_clause(self) -> None:
        """A base-only ledger (no ward, no environment) produces no drama clause."""
        text = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="the Pyromancer",
            outcome=self._outcome_with_damage(24),
            power_ledger=_base_ledger(),
        )
        assert "ward" not in text
        assert "resonance" not in text

    def test_no_target_self_action_unaffected_by_ledger(self) -> None:
        """Self-target/utility path returns early; ledger has no effect there."""
        outcome = ActionOutcome(entity_type="pc", entity_label="Garruk")
        text = render_action_outcome_narration(
            actor_label="Garruk",
            technique_name="Guard Stance",
            target_label=None,
            outcome=outcome,
            power_ledger=_bounce_ledger(),
        )
        assert "Garruk" in text
        assert "Guard Stance" in text
        # Self actions return before the ward clause is applied.
        assert "ward" not in text

    def test_output_ends_with_period(self) -> None:
        """Every narration variant must end with a period."""
        cases: list[tuple[ActionOutcome, PowerLedger | None]] = [
            (self._miss_outcome(), None),
            (self._miss_outcome(), _bounce_ledger()),
            (self._outcome_with_damage(30), None),
            (self._outcome_with_damage(30), _environment_ledger()),
            (self._outcome_with_damage(30), _clean_penetration_ledger()),
        ]
        for outcome, ledger in cases:
            text = render_action_outcome_narration(
                actor_label="Kira",
                technique_name="Frost Bolt",
                target_label="the Pyromancer",
                outcome=outcome,
                power_ledger=ledger,
            )
            assert text.endswith("."), f"Missing period: {text!r}"
