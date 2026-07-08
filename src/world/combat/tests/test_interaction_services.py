"""Tests for combat interaction narration helpers."""

from __future__ import annotations

from django.test import SimpleTestCase

from world.combat.interaction_services import render_combo_finisher_narration


class RenderComboFinisherNarrationTests(SimpleTestCase):
    """Tests for the joint combo finisher narration function."""

    def test_two_contributors_with_target(self) -> None:
        """Two contributors named, total damage summed, target included."""
        result = render_combo_finisher_narration(
            combo_name="Firestorm Fusion",
            contributor_labels=["Kira", "Garruk"],
            target_label="the Pyromancer",
            total_damage=85,
        )
        self.assertEqual(
            result,
            "Kira and Garruk unleash Firestorm Fusion on the Pyromancer for 85 damage.",
        )

    def test_three_contributors_with_target(self) -> None:
        """Three contributors use comma + 'and' formatting."""
        result = render_combo_finisher_narration(
            combo_name="Storm Call",
            contributor_labels=["Kira", "Garruk", "Vex"],
            target_label="the Ogre",
            total_damage=120,
        )
        self.assertEqual(
            result,
            "Kira, Garruk and Vex unleash Storm Call on the Ogre for 120 damage.",
        )

    def test_no_target(self) -> None:
        """No target — self/utility combo."""
        result = render_combo_finisher_narration(
            combo_name="Ward Break",
            contributor_labels=["Kira", "Garruk"],
            target_label=None,
            total_damage=0,
        )
        self.assertEqual(result, "Kira and Garruk unleash Ward Break.")

    def test_signature_clause_appended(self) -> None:
        """Signature flourish clause appended with em-dash."""
        result = render_combo_finisher_narration(
            combo_name="Firestorm Fusion",
            contributor_labels=["Kira", "Garruk"],
            target_label="the Pyromancer",
            total_damage=85,
            signature_clause="their signature move",
        )
        self.assertEqual(
            result,
            "Kira and Garruk unleash Firestorm Fusion on the Pyromancer"
            " for 85 damage — their signature move.",
        )

    def test_single_contributor(self) -> None:
        """Single contributor still works (backward-compatible path)."""
        result = render_combo_finisher_narration(
            combo_name="Solo Strike",
            contributor_labels=["Kira"],
            target_label="the Goblin",
            total_damage=30,
        )
        self.assertEqual(
            result,
            "Kira unleash Solo Strike on the Goblin for 30 damage.",
        )
