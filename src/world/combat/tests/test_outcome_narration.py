"""Unit tests for outcome-narration render helpers — deterministic, no DB."""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from world.combat.interaction_services import (
    render_action_outcome_narration,
    render_clash_outcome_narration,
)
from world.combat.types import ActionOutcome, OpponentDamageResult
from world.magic.narration import fill_narration_placeholders, validate_outcome_narration
from world.scenes.interaction_services import render_challenge_outcome_narration


def _opp_dmg(
    *, damage_dealt: int, defeated: bool = False, opponent_id: int | None = None
) -> OpponentDamageResult:
    return OpponentDamageResult(
        opponent_id=opponent_id,
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


class AuthoredOutcomeNarrationTest(SimpleTestCase):
    """#3554: authored hit/miss text replaces the head, never the ledger."""

    def _hit(self, damage: int = 24) -> ActionOutcome:
        outcome = ActionOutcome(entity_type="pc", entity_label="Kira")
        outcome.damage_results.append(_opp_dmg(damage_dealt=damage))
        return outcome

    def test_hit_text_replaces_head_and_keeps_damage_figure(self) -> None:
        text = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="the Pyromancer",
            outcome=self._hit(),
            hit_text="{actor} hurls a spear of rime at {target}",
        )
        assert text == "Kira hurls a spear of rime at the Pyromancer for 24 damage."

    def test_hit_text_keeps_tail_clauses(self) -> None:
        outcome = ActionOutcome(entity_type="pc", entity_label="Kira")
        outcome.damage_results.append(_opp_dmg(damage_dealt=40, defeated=True))
        text = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="the Pyromancer",
            outcome=outcome,
            hit_text="{actor} hurls a spear of rime at {target}",
        )
        assert text == (
            "Kira hurls a spear of rime at the Pyromancer for 40 damage, defeating them."
        )

    def test_miss_text_replaces_miss_head(self) -> None:
        outcome = ActionOutcome(entity_type="pc", entity_label="Kira")
        outcome.damage_results.append(_opp_dmg(damage_dealt=0))
        text = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="the Pyromancer",
            outcome=outcome,
            hit_text="{actor} hurls a spear of rime at {target}",
            miss_text="{actor}'s rime shatters short of {target}",
        )
        assert text == "Kira's rime shatters short of the Pyromancer."

    def test_blank_text_falls_back_to_default_sentence(self) -> None:
        plain = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="the Pyromancer",
            outcome=self._hit(),
        )
        with_blank = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="the Pyromancer",
            outcome=self._hit(),
            hit_text="",
            miss_text="",
        )
        assert with_blank == plain
        assert "Frost Bolt" in plain

    def test_hit_text_is_ignored_for_untargeted_action(self) -> None:
        outcome = ActionOutcome(entity_type="pc", entity_label="Garruk")
        text = render_action_outcome_narration(
            actor_label="Garruk",
            technique_name="Guard Stance",
            target_label=None,
            outcome=outcome,
            hit_text="{actor} braces against {target}",
        )
        assert text == "Garruk uses Guard Stance."

    def test_stray_braces_survive_substitution(self) -> None:
        assert (
            fill_narration_placeholders("{actor} says {hi} to {target}", actor="A", target="B")
            == "A says {hi} to B"
        )

    def test_validator_requires_both_placeholders(self) -> None:
        validate_outcome_narration("", "hit_narration")
        validate_outcome_narration("{actor} strikes {target}", "hit_narration")
        with self.assertRaises(ValidationError):
            validate_outcome_narration("{actor} strikes", "hit_narration")
        with self.assertRaises(ValidationError):
            validate_outcome_narration("strikes {target}", "hit_narration")


HOUND_ID = 11
WYRM_ID = 12
DRAKE_ID = 13
LABELS = {HOUND_ID: "Hound", WYRM_ID: "Wyrm", DRAKE_ID: "Drake"}


def _area_outcome(*damages: tuple[int, int]) -> ActionOutcome:
    """An outcome with one damage result per ``(opponent_id, damage)`` given."""
    outcome = ActionOutcome(entity_type="pc", entity_label="Vesper")
    for opponent_id, damage in damages:
        outcome.damage_results.append(_opp_dmg(damage_dealt=damage, opponent_id=opponent_id))
    return outcome


class AreaOutcomeNarrationTest(SimpleTestCase):
    """#4842: an area cast names each opponent with its own damage."""

    def _render(self, outcome: ActionOutcome, **extra: object) -> str:
        return render_action_outcome_narration(
            actor_label="Vesper",
            technique_name="Sweep",
            target_label="Hound",
            outcome=outcome,
            target_opponent_id=HOUND_ID,
            opponent_labels=LABELS,
            **extra,
        )

    def test_single_opponent_line_is_unchanged(self) -> None:
        text = self._render(_area_outcome((HOUND_ID, 6)))
        assert text == "Vesper’s Sweep strikes Hound for 6 damage."

    def test_profiles_on_one_opponent_still_sum_into_one_figure(self) -> None:
        text = self._render(_area_outcome((HOUND_ID, 4), (HOUND_ID, 2)))
        assert text == "Vesper’s Sweep strikes Hound for 6 damage."

    def test_two_opponents_each_get_their_own_figure(self) -> None:
        text = self._render(_area_outcome((HOUND_ID, 6), (WYRM_ID, 11)))
        assert text == "Vesper’s Sweep strikes Hound for 6 damage and Wyrm for 11 damage."

    def test_focused_target_is_named_first_whatever_the_result_order(self) -> None:
        text = self._render(_area_outcome((WYRM_ID, 11), (HOUND_ID, 6)))
        assert text == "Vesper’s Sweep strikes Hound for 6 damage and Wyrm for 11 damage."

    def test_three_opponents_read_as_a_series(self) -> None:
        text = self._render(_area_outcome((HOUND_ID, 6), (DRAKE_ID, 4), (WYRM_ID, 11)))
        assert text == (
            "Vesper’s Sweep strikes Hound for 6 damage, Drake for 4 damage and Wyrm for 11 damage."
        )

    def test_authored_hit_text_head_is_kept_for_the_focused_target(self) -> None:
        text = self._render(
            _area_outcome((HOUND_ID, 6), (WYRM_ID, 11)),
            hit_text="{actor} whirls a ring of steel through {target}",
        )
        assert text == (
            "Vesper whirls a ring of steel through Hound for 6 damage and Wyrm for 11 damage."
        )

    def test_opponent_that_took_nothing_is_left_out(self) -> None:
        text = self._render(_area_outcome((HOUND_ID, 6), (WYRM_ID, 0), (DRAKE_ID, 4)))
        assert text == "Vesper’s Sweep strikes Hound for 6 damage and Drake for 4 damage."

    def test_focused_target_that_took_nothing_is_left_out(self) -> None:
        text = self._render(_area_outcome((HOUND_ID, 0), (WYRM_ID, 11)))
        assert text == "Vesper’s Sweep strikes Wyrm for 11 damage."

    def test_tail_and_suffix_clauses_come_once_at_the_end(self) -> None:
        outcome = _area_outcome((HOUND_ID, 6), (WYRM_ID, 11))
        outcome.damage_results[1] = _opp_dmg(damage_dealt=11, defeated=True, opponent_id=WYRM_ID)
        text = self._render(outcome, signature_snippet="a hiss of steel")
        assert text == (
            "Vesper’s Sweep strikes Hound for 6 damage and Wyrm for 11 damage, "
            "defeating them — a hiss of steel."
        )

    def test_without_labels_the_summed_line_stays(self) -> None:
        text = render_action_outcome_narration(
            actor_label="Vesper",
            technique_name="Sweep",
            target_label="Hound",
            outcome=_area_outcome((HOUND_ID, 6), (WYRM_ID, 11)),
        )
        assert text == "Vesper’s Sweep strikes Hound for 17 damage."

    def test_an_opponent_missing_from_the_labels_falls_back_to_the_sum(self) -> None:
        text = render_action_outcome_narration(
            actor_label="Vesper",
            technique_name="Sweep",
            target_label="Hound",
            outcome=_area_outcome((HOUND_ID, 6), (99, 11)),
            target_opponent_id=HOUND_ID,
            opponent_labels=LABELS,
        )
        assert text == "Vesper’s Sweep strikes Hound for 17 damage."
