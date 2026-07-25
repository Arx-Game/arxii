"""Tests for the CombatOpponent.level -> resist-path wiring fix

(#2707 whole-branch-review finding 4).

``_social_combat_difficulty`` (backing Demoralize/Taunt/Parley) obtained a
CombatOpponent's morale defense via
``compute_resist_increment(target.objectdb, effort_level)``. That resolved level
through the objectdb's ``CharacterClassLevel`` rows, which an EPHEMERAL
CombatOpponent (the default -- a fresh CombatNPC objectdb, not a persona-backed
character) has none of, so it always floored at 1 -- ``CombatOpponent.level`` was
silently ignored on this path even though the SAME opponent's offense already
opposed PC checks at its real authored level (via ``level_opposition``). This is
the case that was broken, so it is the case these tests cover: an ephemeral
opponent, never a persona-backed one.
"""

from django.test import TestCase

from world.checks.constants import LEVEL_POINTS_PER_LEVEL
from world.checks.factories import create_resistance_check_types
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.combat.services import _social_combat_difficulty
from world.traits.models import PointConversionRange, TraitType


class SocialCombatDifficultyLevelTests(TestCase):
    """A high-level ephemeral opponent must resist harder than a low-level one."""

    @classmethod
    def setUpTestData(cls):
        create_resistance_check_types()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        cls.encounter = CombatEncounterFactory()

    def test_high_level_ephemeral_opponent_resists_harder_than_low_level(self):
        """The gap this fix closes: without level_override this used to be a tie."""
        low = CombatOpponentFactory(encounter=self.encounter, level=1)
        high = CombatOpponentFactory(encounter=self.encounter, level=20)

        # Confirm the fixture actually is the broken case: an ephemeral opponent
        # with no persona/CharacterClassLevel rows behind its objectdb.
        self.assertTrue(low.objectdb_is_ephemeral)
        self.assertTrue(high.objectdb_is_ephemeral)
        self.assertIsNotNone(low.objectdb)
        self.assertIsNotNone(high.objectdb)

        low_difficulty = _social_combat_difficulty(low)
        high_difficulty = _social_combat_difficulty(high)

        self.assertGreater(high_difficulty, low_difficulty)
        self.assertEqual(high_difficulty - low_difficulty, LEVEL_POINTS_PER_LEVEL * (20 - 1))

    def test_no_target_still_returns_zero(self):
        """Rally targets an ally -- target=None stays a no-op (pre-existing behavior)."""
        self.assertEqual(_social_combat_difficulty(None), 0)
