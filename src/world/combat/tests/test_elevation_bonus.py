"""Tests for the offensive-only elevation bonus (#2011)."""

from django.test import TestCase
from evennia import create_object

from world.areas.positioning.constants import PositionKind
from world.areas.positioning.services import connect_positions, create_position
from world.combat.services import elevation_bonus


class ElevationBonusTest(TestCase):
    """elevation_bonus returns a flat bonus when attacker is elevated and target is not."""

    def setUp(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.factories import wire_elevation_advantage_modifier_target
        from world.mechanics.factories import (
            ModifierSourceFactory,
        )
        from world.mechanics.models import CharacterModifier

        self.room = create_object("typeclasses.rooms.Room", key="ElevBonusRoom", nohome=True)
        self.ground_a = create_position(self.room, "elev_ground_a")
        self.ground_b = create_position(self.room, "elev_ground_b")
        self.elevated = create_position(self.room, "elev_high", kind=PositionKind.ELEVATED)
        self.aerial = create_position(self.room, "elev_sky", kind=PositionKind.AERIAL)
        connect_positions(self.ground_a, self.ground_b, is_passable=True)

        self.sheet = CharacterSheetFactory()

        # Seed the ModifierTarget and create a CharacterModifier row with value 5.
        # Mark the source as achievement_reward=True so the modifier pipeline treats
        # it as a recognized flat-value source (not SOURCE_TYPE_UNKNOWN).
        self.target = wire_elevation_advantage_modifier_target()
        source = ModifierSourceFactory(achievement_reward=True)
        CharacterModifier.objects.create(
            character=self.sheet,
            target=self.target,
            source=source,
            value=5,
        )

    def test_elevated_attacker_ground_target_returns_bonus(self):
        """ELEVATED attacker firing at a ground target gets the bonus."""
        bonus = elevation_bonus(self.sheet, self.elevated, self.ground_a)
        self.assertEqual(bonus, 5)

    def test_aerial_attacker_ground_target_returns_bonus(self):
        """AERIAL attacker firing at a ground target gets the bonus."""
        bonus = elevation_bonus(self.sheet, self.aerial, self.ground_a)
        self.assertEqual(bonus, 5)

    def test_ground_attacker_elevated_target_returns_zero(self):
        """Ground attacker firing up at an elevated target gets NO penalty."""
        self.assertEqual(elevation_bonus(self.sheet, self.ground_a, self.elevated), 0)

    def test_both_elevated_returns_zero(self):
        """Both elevated — no advantage."""
        self.assertEqual(elevation_bonus(self.sheet, self.elevated, self.elevated), 0)

    def test_both_ground_returns_zero(self):
        """Both ground — no advantage."""
        self.assertEqual(elevation_bonus(self.sheet, self.ground_a, self.ground_b), 0)
