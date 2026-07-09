"""Tests for equipment flourish in combat narration (#2023)."""

from __future__ import annotations

from django.test import TestCase

from world.combat.interaction_services import render_action_outcome_narration
from world.combat.types import ActionOutcome


def _outcome_with_damage(damage: int = 10) -> ActionOutcome:
    """Build a minimal ActionOutcome with one damage result."""
    result = ActionOutcome(entity_type="pc", entity_label="Kira")
    result.damage_results = [type("R", (), {"damage_dealt": damage, "defeated": False})()]
    return result


class WeaponFlourishNarrationTests(TestCase):
    """weapon_flourish appears as em-dash clause in the hit narration."""

    def test_weapon_flourish_appended_to_hit_line(self):
        narration = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="Ogre",
            outcome=_outcome_with_damage(24),
            weapon_flourish="the blade sings as it bites",
        )
        assert "— the blade sings as it bites" in narration
        assert "24 damage" in narration

    def test_no_weapon_flourish_omits_clause(self):
        narration = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="Ogre",
            outcome=_outcome_with_damage(24),
            weapon_flourish=None,
        )
        assert "—" not in narration

    def test_armor_flourish_appended_to_hit_line(self):
        narration = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="Ogre",
            outcome=_outcome_with_damage(10),
            armor_flourish="the plate turns the blow aside",
        )
        assert "— the plate turns the blow aside" in narration

    def test_weapon_and_armor_flourish_both_appended(self):
        narration = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="Ogre",
            outcome=_outcome_with_damage(10),
            weapon_flourish="the blade sings",
            armor_flourish="the plate holds",
        )
        assert "— the blade sings" in narration
        assert "— the plate holds" in narration

    def test_flourish_on_miss_line(self):
        """Flourish appears even on a miss."""
        outcome = ActionOutcome(entity_type="pc", entity_label="Kira")
        narration = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="Ogre",
            outcome=outcome,
            weapon_flourish="the blade hums",
        )
        assert "— the blade hums" in narration
        assert "misses" in narration
