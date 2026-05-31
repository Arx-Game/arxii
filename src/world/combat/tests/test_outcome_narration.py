"""Unit tests for outcome-narration render helpers — deterministic, no DB."""

from django.test import SimpleTestCase

from world.combat.interaction_services import (
    render_action_outcome_narration,
    render_challenge_outcome_narration,
    render_clash_outcome_narration,
)
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


class ChallengeOutcomeNarrationTest(SimpleTestCase):
    def test_names_actor_challenge_and_approach(self) -> None:
        text = render_challenge_outcome_narration(
            actor_label="Kira",
            challenge_name="Scale the Wall",
            approach_name="Athletics",
            outcome_label="Marginal Success",
            success_level=1,
        )
        assert "Kira" in text
        assert "Scale the Wall" in text
        assert "Athletics" in text

    def test_success_reads_as_success(self) -> None:
        text = render_challenge_outcome_narration(
            actor_label="Kira",
            challenge_name="Scale the Wall",
            approach_name="Athletics",
            outcome_label="Decisive Success",
            success_level=2,
        )
        assert "succeed" in text.lower() or "success" in text.lower()

    def test_failure_reads_as_failure(self) -> None:
        text = render_challenge_outcome_narration(
            actor_label="Kira",
            challenge_name="Scale the Wall",
            approach_name="Athletics",
            outcome_label="Failure",
            success_level=-1,
        )
        assert "fail" in text.lower()

    def test_deterministic(self) -> None:
        kwargs = {
            "actor_label": "Kira",
            "challenge_name": "Scale the Wall",
            "approach_name": "Athletics",
            "outcome_label": "Marginal Success",
            "success_level": 1,
        }
        assert render_challenge_outcome_narration(**kwargs) == render_challenge_outcome_narration(
            **kwargs
        )


class ClashOutcomeNarrationTest(SimpleTestCase):
    def test_names_opponent_and_flavor(self) -> None:
        text = render_clash_outcome_narration(
            flavor_label="Break",
            opponent_label="the Pyromancer",
            resolution_tier="PC_DECISIVE",
        )
        assert "the Pyromancer" in text
        assert "Break" in text

    def test_pc_decisive_favors_casters(self) -> None:
        text = render_clash_outcome_narration(
            flavor_label="Clash",
            opponent_label="the Pyromancer",
            resolution_tier="PC_DECISIVE",
        )
        assert "decisive" in text.lower()

    def test_npc_decisive_favors_opponent(self) -> None:
        text = render_clash_outcome_narration(
            flavor_label="Ward",
            opponent_label="the Pyromancer",
            resolution_tier="NPC_DECISIVE",
        )
        assert "the Pyromancer" in text
        assert "decisive" in text.lower()

    def test_each_tier_renders_nonempty(self) -> None:
        for tier in (
            "PC_DECISIVE",
            "PC_MARGINAL",
            "MUTUAL",
            "NPC_MARGINAL",
            "NPC_DECISIVE",
            "ABANDONED",
        ):
            text = render_clash_outcome_narration(
                flavor_label="Clash",
                opponent_label="the Pyromancer",
                resolution_tier=tier,
            )
            assert text, f"empty narration for tier {tier}"

    def test_consequence_label_appended_when_present(self) -> None:
        text = render_clash_outcome_narration(
            flavor_label="Break",
            opponent_label="the Pyromancer",
            resolution_tier="PC_DECISIVE",
            consequence_label="Stagger",
        )
        assert "Stagger" in text

    def test_deterministic(self) -> None:
        kwargs = {
            "flavor_label": "Break",
            "opponent_label": "the Pyromancer",
            "resolution_tier": "PC_MARGINAL",
            "consequence_label": "Stagger",
        }
        assert render_clash_outcome_narration(**kwargs) == render_clash_outcome_narration(**kwargs)
