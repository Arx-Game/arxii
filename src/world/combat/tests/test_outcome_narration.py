"""Unit tests for render_action_outcome_narration — deterministic, no DB."""

from django.test import SimpleTestCase

from world.combat.interaction_services import render_action_outcome_narration
from world.combat.types import ActionOutcome, OpponentDamageResult


def _opp_dmg(*, damage_dealt: int, defeated: bool = False) -> OpponentDamageResult:
    return OpponentDamageResult(
        damage_dealt=damage_dealt,
        health_damaged=damage_dealt > 0,
        probed=False,
        probing_increment=0,
        defeated=defeated,
    )


class OutcomeNarrationTest(SimpleTestCase):
    def test_plain_damage(self) -> None:
        outcome = ActionOutcome(entity_type="pc", entity_label="Kira")
        outcome.damage_results.append(_opp_dmg(damage_dealt=24))
        text = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="the Pyromancer",
            outcome=outcome,
        )
        assert "Kira" in text
        assert "Frost Bolt" in text
        assert "24" in text
        assert "the Pyromancer" in text

    def test_zero_damage_is_a_miss(self) -> None:
        outcome = ActionOutcome(entity_type="pc", entity_label="Kira")
        outcome.damage_results.append(_opp_dmg(damage_dealt=0))
        text = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="the Pyromancer",
            outcome=outcome,
        )
        assert "miss" in text.lower()

    def test_defeat_clause(self) -> None:
        outcome = ActionOutcome(entity_type="pc", entity_label="Kira")
        outcome.damage_results.append(_opp_dmg(damage_dealt=40, defeated=True))
        text = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="the Pyromancer",
            outcome=outcome,
        )
        assert "defeat" in text.lower() or "fell" in text.lower()

    def test_no_target_self_action(self) -> None:
        outcome = ActionOutcome(entity_type="pc", entity_label="Garruk")
        text = render_action_outcome_narration(
            actor_label="Garruk",
            technique_name="Guard Stance",
            target_label=None,
            outcome=outcome,
        )
        assert "Garruk" in text
        assert "Guard Stance" in text

    def test_deterministic(self) -> None:
        outcome = ActionOutcome(entity_type="pc", entity_label="Kira")
        outcome.damage_results.append(_opp_dmg(damage_dealt=12))
        kwargs = {
            "actor_label": "Kira",
            "technique_name": "Frost Bolt",
            "target_label": "the Pyromancer",
            "outcome": outcome,
        }
        assert render_action_outcome_narration(**kwargs) == render_action_outcome_narration(
            **kwargs
        )
