"""Journey test: a physical attack rolls against the target, not against zero
(#2707 Task 6).

Before this task, ``CombatTechniqueResolver._roll_check`` rolled the offense
check against ``target_difficulty=0`` regardless of who was targeted -- the
motivating bug for #2707: a level 1 character stabbing a level 15 opponent
rolled exactly as easily as stabbing a level 1 one. This drives
``CombatTechniqueResolver`` through ``resolve_round`` -- the same
round-resolution seam ``test_combo_journey.py`` uses -- rather than calling
``perform_check`` directly, because round resolution is the seam that proves
the user journey.

Assertions are made on the ``CheckResult.success_level`` (the outcome tier: -2
Critical Failure .. 2 Critical Success), never on damage. The chip-damage value
a partial success deals against a much-higher-level target is an authored
``DamageSuccessLevelMultiplier`` row (see ``world/seeds/checks.py``'s
``_DIRE_BANDS`` docstring) that this repo does not seed, so a damage assertion
would test unseeded content and prove nothing.

The penetration-check assertions below reuse ``penetration_helpers._build_resolver``
(the same builder ``test_penetration.py`` uses) rather than full round
resolution -- one layer below round resolution, but still driving the real
``CombatTechniqueResolver.__call__`` seam, not a bare ``perform_check`` call.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from actions.factories import ActionTemplateFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.services import level_opposition, perform_check as real_perform_check
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.combat.constants import ActionCategory, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolFactory,
    wire_penetration_check_type,
)
from world.combat.models import CombatRoundAction
from world.combat.services import get_penetration_check_type, resolve_round
from world.combat.tests.penetration_helpers import _build_resolver, _ledger
from world.conditions.factories import wire_penetration_factors
from world.fatigue.models import FatiguePool
from world.magic.factories import (
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import RoundStatus
from world.seeds.checks import seed_check_resolution_tables
from world.vitals.models import CharacterVitals


class LevelOpposedOffenseJourneyTests(TestCase):
    """The offense roll's difficulty comes from the focused opponent's level."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_check_resolution_tables()
        cls.effect = EffectTypeFactory(name="Journey Strike", base_power=20)
        cls.gift = GiftFactory()
        cls.check_type = CheckTypeFactory(name="Journey Offense Check")
        cls.character_class = CharacterClassFactory()

    def setUp(self) -> None:
        from world.checks.models import CheckType
        from world.traits.models import ResultChart

        CheckType.flush_instance_cache()
        ResultChart.clear_cache()

    def _offense_success_level(self, *, pc_level: int | None, opp_level: int, roll: int) -> int:
        """Resolve one fresh round: a lone PC's technique against a lone opponent.

        Returns the CheckResult.success_level the round's offense roll actually
        produced. ``pc_level`` is None to leave the attacker at the
        ``get_character_path_level`` fallback of 1 (no CharacterClassLevel row).
        The opponent's threat pool has no entries, so it never attacks back --
        the round resolves exactly one offense check.
        """
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        empty_pool = ThreatPoolFactory()
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=1000,
            max_health=1000,
            threat_pool=empty_pool,
            level=opp_level,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        CharacterAnimaFactory(character=sheet, current=50, maximum=50)
        FatiguePool.objects.create(character_sheet=sheet)
        CharacterEngagementFactory(character=sheet)
        if pc_level is not None:
            CharacterClassLevelFactory(
                character=sheet,
                character_class=self.character_class,
                level=pc_level,
                is_primary=True,
            )
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect,
            action_template=ActionTemplateFactory(check_type=self.check_type),
        )
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opponent,
        )

        captured: list = []

        def _spy(*args, **kwargs):
            result = real_perform_check(*args, **kwargs)
            captured.append(result)
            return result

        with (
            patch("world.checks.services.random.randint", return_value=roll),
            patch("world.combat.services.perform_check", side_effect=_spy),
        ):
            resolve_round(encounter)

        self.assertEqual(len(captured), 1, "expected exactly one offense check to roll")
        return captured[0].success_level

    def test_low_level_attacker_produces_lower_success_against_higher_level_target(self) -> None:
        rolls = [10, 50, 99]
        against_low_opp = [
            self._offense_success_level(pc_level=None, opp_level=1, roll=roll) for roll in rolls
        ]
        against_high_opp = [
            self._offense_success_level(pc_level=None, opp_level=15, roll=roll) for roll in rolls
        ]
        for success_vs_high, success_vs_low in zip(against_high_opp, against_low_opp, strict=True):
            self.assertLessEqual(success_vs_high, success_vs_low)
        self.assertLess(sum(against_high_opp), sum(against_low_opp))

    def test_low_level_attacker_still_connects_against_high_level_target_on_a_good_roll(
        self,
    ) -> None:
        """It degrades, it does not stonewall: a good roll still lands a non-failure."""
        success_level = self._offense_success_level(pc_level=None, opp_level=15, roll=99)
        self.assertGreaterEqual(success_level, 0)

    def test_high_level_attacker_lands_markedly_better_against_a_low_level_target(self) -> None:
        rolls = [10, 50, 99]
        against_low_opp = [
            self._offense_success_level(pc_level=15, opp_level=1, roll=roll) for roll in rolls
        ]
        against_high_opp = [
            self._offense_success_level(pc_level=15, opp_level=15, roll=roll) for roll in rolls
        ]
        for success_vs_low, success_vs_high in zip(against_low_opp, against_high_opp, strict=True):
            self.assertGreater(success_vs_low, success_vs_high)
        # "Markedly" -- at least one roll clears a full outcome tier, not a hair's difference.
        self.assertTrue(
            any(lo - hi >= 2 for lo, hi in zip(against_low_opp, against_high_opp, strict=True))
        )


@override_settings(SEED_SAMPLE_CONTENT=True)  # wire_penetration_check_type gates on #2698
class LevelOpposedPenetrationJourneyTests(TestCase):
    """The ward contest's difficulty is additive: ward + level_opposition (#2707 Task 6,
    decision 6)."""

    @classmethod
    def setUpTestData(cls) -> None:
        wire_penetration_factors()
        wire_penetration_check_type()

    def _target_difficulty_for(
        self, *, target_level: int, barrier_strength: int = 10
    ) -> tuple[int, object]:
        resolver = _build_resolver(barrier_strength=barrier_strength)
        target = resolver.action.focused_opponent_target
        target.level = target_level
        target.save(update_fields=["level"])
        with patch("world.combat.services.perform_check") as mock_pen:
            mock_pen.return_value = MagicMock(success_level=1)
            resolver(power=20, ledger=_ledger(20))
        return mock_pen.call_args.kwargs["target_difficulty"], target

    def test_penetrating_a_higher_level_wards_ward_is_harder(self) -> None:
        low, _ = self._target_difficulty_for(target_level=1)
        high, _ = self._target_difficulty_for(target_level=15)
        self.assertGreater(high, low)

    def test_level_term_is_additive_on_top_of_the_ward(self) -> None:
        """Decision 6: the level term adds to barrier_strength, never replaces it."""
        difficulty, target = self._target_difficulty_for(target_level=5, barrier_strength=10)
        pen_check_type = get_penetration_check_type()
        expected_level_term = level_opposition(pen_check_type, level=5, character=target.objectdb)
        self.assertEqual(difficulty, 10 + expected_level_term)
        # The ward still contributes on its own -- the level term didn't replace it.
        self.assertGreater(difficulty, expected_level_term)
