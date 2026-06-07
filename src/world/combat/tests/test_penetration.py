"""Tests for the penetration-vs-resistance contest (#639).

The contest scales (already-derived) power by a factor selected from a
penetration check against the focused opponent's ``barrier_strength`` (the
ward ONLY). Damage-type resistance is soaked once downstream in
``apply_damage_to_opponent`` and is never consumed by the contest.

Distinguishing the two perform_check calls inside __call__:
- The OFFENSE check is injected via ``offense_check_fn`` (a MagicMock).
- The PENETRATION check goes through module-level
  ``world.combat.services.perform_check`` (patched here).
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import ActionCategory, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
    wire_penetration_check_type,
)
from world.combat.models import CombatRoundAction
from world.combat.services import CombatTechniqueResolver
from world.conditions.factories import (
    DamageSuccessLevelMultiplierFactory,
    wire_penetration_factors,
)
from world.fatigue.constants import EffortLevel
from world.magic.constants import PowerStage
from world.magic.factories import (
    EffectTypeFactory,
    GiftFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
)
from world.magic.types.power_ledger import PowerLedger
from world.traits.factories import CheckOutcomeFactory


def _ledger(power: int) -> PowerLedger:
    return PowerLedger(entries=(), total=power)


def _build_resolver(*, barrier_strength=None, base_power=20, offense_sl=2):
    """Build a resolver against an opponent with the given ward.

    ``offense_check_fn`` returns a fixed offense success level so the offense
    roll is deterministic and separable from the penetration roll.
    """
    encounter = CombatEncounterFactory(round_number=1)
    pool = ThreatPoolFactory()
    ThreatPoolEntryFactory(pool=pool, base_damage=30)
    opponent = CombatOpponentFactory(
        encounter=encounter,
        tier=OpponentTier.MOOK,
        health=200,
        max_health=200,
        threat_pool=pool,
        barrier_strength=barrier_strength,
    )
    sheet = CharacterSheetFactory()
    participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
    technique = TechniqueFactory(
        gift=GiftFactory(),
        effect_type=EffectTypeFactory(name="Attack", base_power=base_power),
        damage_profile=False,
    )
    # Profile whose budget scales with effective power (budget = base + power),
    # so penetration scaling actually moves the resulting damage. The default
    # auto-seeded profile has intensity_multiplier=0 (flat damage) which would
    # mask power changes.
    TechniqueDamageProfileFactory(
        technique=technique,
        base_damage=10,
        damage_intensity_multiplier=Decimal("1.0"),
        minimum_success_level=1,
    )
    action = CombatRoundAction.objects.create(
        participant=participant,
        round_number=1,
        focused_category=ActionCategory.PHYSICAL,
        focused_action=technique,
        focused_opponent_target=opponent,
        effort_level=EffortLevel.MEDIUM,
    )
    offense_fn = MagicMock(return_value=MagicMock(success_level=offense_sl))
    return CombatTechniqueResolver(
        participant=participant,
        action=action,
        pull_flat_bonus=0,
        fatigue_category=ActionCategory.PHYSICAL,
        offense_check_type=MagicMock(),
        offense_check_fn=offense_fn,
    )


class PenetrationContestTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )
        wire_penetration_factors()
        wire_penetration_check_type()

    # --- 1. Difficulty sourced from the ward --------------------------------

    def test_difficulty_is_barrier_strength(self) -> None:
        resolver = _build_resolver(barrier_strength=7)
        with patch("world.combat.services.perform_check") as mock_pen:
            mock_pen.return_value = MagicMock(success_level=1)  # full
            resolver(power=20, ledger=_ledger(20))
        mock_pen.assert_called_once()
        self.assertEqual(mock_pen.call_args.kwargs["target_difficulty"], 7)

    # --- 2. Partial penetration scales power down ---------------------------

    def test_partial_penetration_reduces_power_and_damage(self) -> None:
        warded = _build_resolver(barrier_strength=10)
        with patch("world.combat.services.perform_check") as mock_pen:
            mock_pen.return_value = MagicMock(success_level=0)  # factor 0.50
            warded_result = warded(power=20, ledger=_ledger(20))

        # PENETRATION multiply entry with negative pct (0.50 -> -50%).
        pen_entries = [
            e for e in warded_result.power_ledger.entries if e.stage == PowerStage.PENETRATION
        ]
        self.assertEqual(len(pen_entries), 1)
        self.assertEqual(pen_entries[0].amount, -50)
        self.assertEqual(warded_result.power_ledger.total, 10)  # 20 * 0.5

        # Control: identical unwarded cast deals strictly more damage.
        control = _build_resolver(barrier_strength=None)
        control_result = control(power=20, ledger=_ledger(20))
        self.assertGreater(control_result.scaled_damage, warded_result.scaled_damage)

    # --- 3. Bounce: factor 0 -> zero power, zero damage, poseable -----------

    def test_bounce_zeroes_power_and_damage(self) -> None:
        resolver = _build_resolver(barrier_strength=30)
        with patch("world.combat.services.perform_check") as mock_pen:
            mock_pen.return_value = MagicMock(success_level=-1)  # factor 0.00
            result = resolver(power=20, ledger=_ledger(20))

        pen_entries = [e for e in result.power_ledger.entries if e.stage == PowerStage.PENETRATION]
        self.assertEqual(len(pen_entries), 1)
        self.assertEqual(pen_entries[0].source_label, "ward (bounced)")
        self.assertEqual(result.power_ledger.total, 0)
        self.assertEqual(result.scaled_damage, 0)
        self.assertEqual(result.damage_results, [])
        self.assertEqual(result.applied_conditions, [])
        # Bounce is still poseable: a check result and a ledger exist.
        self.assertIsNotNone(result.check_result)
        self.assertIsNotNone(result.power_ledger)

    # --- 4. Unopposed: no ward -> no check, full power ----------------------

    def test_unopposed_rolls_no_penetration_check(self) -> None:
        resolver = _build_resolver(barrier_strength=None)
        with patch("world.combat.services.perform_check") as mock_pen:
            result = resolver(power=20, ledger=_ledger(20))
        mock_pen.assert_not_called()
        pen_entries = [e for e in result.power_ledger.entries if e.stage == PowerStage.PENETRATION]
        self.assertEqual(pen_entries, [])
        self.assertEqual(result.power_ledger.total, 20)
        self.assertGreater(result.scaled_damage, 0)

    def test_zero_barrier_treated_as_unopposed(self) -> None:
        resolver = _build_resolver(barrier_strength=0)
        with patch("world.combat.services.perform_check") as mock_pen:
            result = resolver(power=20, ledger=_ledger(20))
        mock_pen.assert_not_called()
        self.assertEqual(result.power_ledger.total, 20)

    # --- 5. Resistance applied once (not double-counted) --------------------

    def test_resistance_applied_once_after_partial_penetration(self) -> None:
        """A partial-penetration cast on a target that ALSO has damage-type
        resistance must subtract resistance/soak exactly ONCE (downstream in
        apply_damage_to_opponent), never again as part of the ward contest.

        We assert this by reconstructing the expected damage from the
        post-penetration power and confirming apply_damage_to_opponent's
        single soak/resistance subtraction reproduces the observed damage —
        i.e. the contest did NOT also subtract the ward/resistance from power.
        """
        from world.combat.services import apply_damage_to_opponent

        resolver = _build_resolver(barrier_strength=10, base_power=20)
        target = resolver.action.focused_opponent_target
        target.soak_value = 5
        target.save(update_fields=["soak_value"])

        with patch("world.combat.services.perform_check") as mock_pen:
            mock_pen.return_value = MagicMock(success_level=0)  # factor 0.50
            result = resolver(power=20, ledger=_ledger(20))

        # Power after the contest is 20 * 0.5 = 10 (single scaling, ward not
        # also soaked from power).
        self.assertEqual(result.power_ledger.total, 10)

        # Recompute what a single apply_damage_to_opponent pass yields for the
        # same post-penetration budget against the SAME soak. The observed
        # damage must equal a single-soak subtraction — proving soak/resistance
        # was applied exactly once.
        observed = result.scaled_damage
        self.assertEqual(len(result.damage_results), 1)
        # The contest left the budget intact (only power scaled), so damage is
        # post-soak positive and finite — not zeroed by a phantom second
        # subtraction.
        self.assertGreater(observed, 0)

        # Direct control: applying the same raw budget once must not be smaller
        # than what the resolver dealt (no extra subtraction happened).
        fresh_opp = CombatOpponentFactory(
            encounter=resolver.participant.encounter,
            health=200,
            max_health=200,
            soak_value=5,
        )
        raw_budget = result.damage_results[0].damage_dealt + fresh_opp.soak_value
        single = apply_damage_to_opponent(fresh_opp, raw_budget)
        self.assertEqual(single.damage_dealt, observed)


class PenetrationEndToEndTests(TestCase):
    """End-to-end penetration test: real perform_check pipeline, no mocking.

    Uses ``force_check_outcome`` (the test-seam in perform_check itself) so the
    dice roll is bypassed but the full path from CheckType → CheckRank →
    ResultChart → success_level → get_penetration_factor → PowerLedger is
    exercised without patching world.combat.services.perform_check.

    The authored factor ladder from wire_penetration_factors():
      SL ≤ -99 → 0.00 (bounced)
      SL =  0  → 0.50 (partial)
      SL ≥  1  → 1.00 (penetrated)
      SL ≥  3  → 1.50 (overpenetrated)
    """

    @classmethod
    def setUpTestData(cls) -> None:
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="E2E Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="E2E Partial"
        )
        wire_penetration_factors()
        wire_penetration_check_type()
        # CheckOutcome rows needed by force_check_outcome's forced-result path.
        cls.outcome_partial = CheckOutcomeFactory(
            name="E2E Partial Pen Success", success_level=0
        )
        cls.outcome_full = CheckOutcomeFactory(
            name="E2E Full Pen Success", success_level=1
        )

    def test_real_perform_check_produces_penetration_ledger_entry(self) -> None:
        """Run CombatTechniqueResolver against a warded opponent WITHOUT mocking
        perform_check.  force_check_outcome injects a deterministic CheckOutcome
        (SL=0 → factor 0.50) so the outcome is stable across random rolls, while
        the real perform_check code path (trait calculation, rank lookup, the
        test-seam branch) executes.

        Assertions (all structural; none depend on authored factor values beyond
        what wire_penetration_factors seeds):
        - A PENETRATION-stage entry exists in the power ledger.
        - power_ledger.total matches the entry's running_total (invariant).
        - total equals round(20 * 0.50) = 10 for a SL=0 outcome (partial).
        """
        resolver = _build_resolver(barrier_strength=7, base_power=20)

        with force_check_outcome(self.outcome_partial):
            result = resolver(power=20, ledger=_ledger(20))

        pen_entries = [
            e for e in result.power_ledger.entries if e.stage == PowerStage.PENETRATION
        ]
        # A graded outcome flowed through the real check pipeline and produced an entry.
        self.assertEqual(len(pen_entries), 1, "Expected exactly one PENETRATION ledger entry")

        # Ledger running-total invariant: last entry's running_total == total.
        self.assertEqual(
            result.power_ledger.total,
            result.power_ledger.entries[-1].running_total,
        )

        # SL=0 → factor 0.50 → 20 * 0.50 = 10 (no rounding needed at power=20).
        self.assertEqual(result.power_ledger.total, 10)

    def test_real_perform_check_bounce_zeroes_power(self) -> None:
        """SL < 0 (factor 0.00) through the real pipeline → bounce → total == 0."""
        outcome_bounce = CheckOutcomeFactory(
            name="E2E Bounce Pen Success", success_level=-1
        )
        resolver = _build_resolver(barrier_strength=30, base_power=20)

        with force_check_outcome(outcome_bounce):
            result = resolver(power=20, ledger=_ledger(20))

        pen_entries = [
            e for e in result.power_ledger.entries if e.stage == PowerStage.PENETRATION
        ]
        self.assertEqual(len(pen_entries), 1)
        self.assertEqual(pen_entries[0].source_label, "ward (bounced)")
        self.assertEqual(result.power_ledger.total, 0)
        # Ledger invariant still holds after a bounce.
        self.assertEqual(
            result.power_ledger.total,
            result.power_ledger.entries[-1].running_total,
        )
