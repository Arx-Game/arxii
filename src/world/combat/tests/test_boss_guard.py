"""Tests for the boss wall-breaker combo authoring guard (#2051)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.combat.constants import OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    ComboDefinitionFactory,
    ComboSlotFactory,
)
from world.magic.factories import EffectTypeFactory


class BossWallBreakerGuardTests(TestCase):
    """A BOSS-tier opponent with a legend-paying aftermath requires a wall_breaker_combo (#2051)."""

    def _make_boss_with_legend_aftermath(self, *, wall_breaker_combo=None):
        """Create a BOSS opponent whose aftermath_pool pays legend."""
        from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
        from world.checks.constants import EffectType
        from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
        from world.traits.factories import CheckOutcomeFactory

        encounter = CombatEncounterFactory()
        outcome_tier = CheckOutcomeFactory()
        pool = ConsequencePoolFactory()
        consequence = ConsequenceFactory(outcome_tier=outcome_tier)
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.LEGEND_AWARD,
        )
        return CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            aftermath_pool=pool,
            wall_breaker_combo=wall_breaker_combo,
        )

    def _make_two_slot_combo(self):
        """Create a valid 2-slot ComboDefinition."""
        combo = ComboDefinitionFactory()
        ComboSlotFactory(combo=combo, slot_number=1, required_action_type=EffectTypeFactory())
        ComboSlotFactory(combo=combo, slot_number=2, required_action_type=EffectTypeFactory())
        return combo

    def test_boss_without_wall_breaker_rejected(self) -> None:
        """A BOSS opponent with legend aftermath but no wall_breaker_combo fails validation."""
        opp = self._make_boss_with_legend_aftermath(wall_breaker_combo=None)
        with self.assertRaises(ValidationError):
            opp.clean()

    def test_boss_with_wall_breaker_accepted(self) -> None:
        """A BOSS opponent with a valid 2-slot wall_breaker_combo passes validation."""
        combo = self._make_two_slot_combo()
        opp = self._make_boss_with_legend_aftermath(wall_breaker_combo=combo)
        opp.clean()  # should not raise

    def test_non_boss_without_wall_breaker_accepted(self) -> None:
        """A non-BOSS opponent with legend aftermath needs no wall_breaker_combo."""
        from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
        from world.checks.constants import EffectType
        from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
        from world.traits.factories import CheckOutcomeFactory

        encounter = CombatEncounterFactory()
        outcome_tier = CheckOutcomeFactory()
        pool = ConsequencePoolFactory()
        consequence = ConsequenceFactory(outcome_tier=outcome_tier)
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.LEGEND_AWARD,
        )
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.ELITE,  # not BOSS
            aftermath_pool=pool,
        )
        opp.clean()  # should not raise

    def test_boss_without_legend_aftermath_accepted(self) -> None:
        """A BOSS opponent with no aftermath_pool needs no wall_breaker_combo."""
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            aftermath_pool=None,
        )
        opp.clean()  # should not raise

    def test_boss_with_single_slot_wall_breaker_rejected(self) -> None:
        """A BOSS opponent with a 1-slot wall_breaker_combo fails validation."""
        combo = ComboDefinitionFactory()
        ComboSlotFactory(combo=combo, slot_number=1, required_action_type=EffectTypeFactory())
        opp = self._make_boss_with_legend_aftermath(wall_breaker_combo=combo)
        with self.assertRaises(ValidationError):
            opp.clean()
