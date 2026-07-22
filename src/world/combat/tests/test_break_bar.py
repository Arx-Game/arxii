"""Tests for break-bar assessment: diversity-weighted accrual, the lieutenant

gate, the pacing floor, and the break celebration (#2642).

The pre-#2642 combo path and flat distinct-PC/distinct-effect-type chip are
replaced by a diversity-weighted formula — see ``assess_break_bar`` and
``docs/adr/0155-boss-fight-structure-diversity-weighted-accrual.md``. Three of
the original tests below have updated expected values (documented inline)
because the flat chip they exercised no longer exists.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.combat.constants import BreakContributionKind, ClashResolution, OpponentTier
from world.combat.factories import (
    BossOpponentFactory,
    ClashContributionFactory,
    ClashRoundFactory,
    CombatEncounterFactory,
    CombatOpponentActionFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ComboDefinitionFactory,
    EngagementLockFactory,
    LockClashFactory,
)
from world.combat.models import BreakBarContribution
from world.combat.services import (
    _active_reinforcer_count,
    assess_break_bar,
    minimum_break_bar_threshold,
)
from world.combat.types import ActionOutcome, OpponentDamageResult
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.factories import EffectTypeFactory
from world.scenes.constants import InteractionMode
from world.scenes.models import Interaction


def _dmg_result(opponent_id, damage_dealt=10):
    return OpponentDamageResult(
        damage_dealt=damage_dealt,
        health_damaged=True,
        probed=False,
        probing_increment=0,
        defeated=False,
        opponent_id=opponent_id,
    )


class BreakBarComboPathTests(TestCase):
    def test_combo_damages_break_bar(self):
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            break_bar_threshold=30,
            break_bar_current=30,
            vulnerability_rounds=2,
            vulnerability_rounds_remaining=0,
        )
        combo = ComboDefinitionFactory(bonus_damage=15)
        effect_type = EffectTypeFactory()
        participant = CombatParticipantFactory(encounter=encounter)
        outcome = ActionOutcome(
            entity_type="pc",
            entity_label="PC1",
            combo_used=combo,
            damage_results=[_dmg_result(opp.pk)],
            participant_id=participant.pk,
            effect_type_id=effect_type.pk,
        )
        assess_break_bar(encounter, [outcome])
        opp.refresh_from_db()
        # Pre-#2642: only bonus_damage counted (15) — the chip path required
        # >=2 distinct PCs, which a solo combo never satisfies.
        # Post-#2642: the same outcome also persists a DAMAGE row (diversity
        # accrual has no per-actor cap) alongside the COMBO row, and each of
        # those two (kind, effect_type) pairs is the encounter's first
        # occurrence — novelty-doubled. 2 (COMBO, novel) + 2 (DAMAGE, novel)
        # + 15 (bonus_damage) = 19; 30 - 19 = 11.
        self.assertEqual(opp.break_bar_current, 11)

    def test_break_bar_breaking_opens_window(self):
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            break_bar_threshold=10,
            break_bar_current=10,
            vulnerability_rounds=2,
            vulnerability_rounds_remaining=0,
            vulnerability_intensity_bonus=2,
        )
        combo = ComboDefinitionFactory(bonus_damage=15)
        outcome = ActionOutcome(
            entity_type="pc",
            entity_label="PC1",
            combo_used=combo,
            damage_results=[_dmg_result(opp.pk)],
            participant_id=CombatParticipantFactory(encounter=encounter).pk,
            effect_type_id=EffectTypeFactory().pk,
        )
        assess_break_bar(encounter, [outcome])
        opp.refresh_from_db()
        self.assertEqual(opp.break_bar_current, 0)
        self.assertEqual(opp.vulnerability_rounds_remaining, 2)

    def test_no_bar_is_noop(self):
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            break_bar_threshold=0,
            break_bar_current=0,
        )
        combo = ComboDefinitionFactory(bonus_damage=15)
        outcome = ActionOutcome(
            entity_type="pc",
            entity_label="PC1",
            combo_used=combo,
            damage_results=[_dmg_result(opp.pk)],
            participant_id=1,
            effect_type_id=1,
        )
        assess_break_bar(encounter, [outcome])
        opp.refresh_from_db()
        self.assertEqual(opp.vulnerability_rounds_remaining, 0)


class BreakBarDistinctPathTests(TestCase):
    def test_two_distinct_pcs_distinct_effect_types_chips_bar(self):
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            break_bar_threshold=5,
            break_bar_current=5,
            vulnerability_rounds=2,
            vulnerability_rounds_remaining=0,
        )
        outcomes = [
            ActionOutcome(
                entity_type="pc",
                entity_label="PC1",
                damage_results=[_dmg_result(opp.pk)],
                participant_id=CombatParticipantFactory(encounter=encounter).pk,
                effect_type_id=EffectTypeFactory().pk,
            ),
            ActionOutcome(
                entity_type="pc",
                entity_label="PC2",
                damage_results=[_dmg_result(opp.pk)],
                participant_id=CombatParticipantFactory(encounter=encounter).pk,
                effect_type_id=EffectTypeFactory().pk,
            ),
        ]
        assess_break_bar(encounter, outcomes)
        opp.refresh_from_db()
        # Pre-#2642: the flat chip fired once (1). Post-#2642: 2 distinct
        # (actor, DAMAGE) pairs = 2 base units, each pair's effect_type is the
        # encounter's first occurrence = +2 novelty bonus. 2 + 2 = 4; 5-4=1.
        self.assertEqual(opp.break_bar_current, 1)

    def test_same_pc_does_not_chip_bar(self):
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            break_bar_threshold=5,
            break_bar_current=5,
            vulnerability_rounds=2,
            vulnerability_rounds_remaining=0,
        )
        pc1 = CombatParticipantFactory(encounter=encounter)
        outcomes = [
            ActionOutcome(
                entity_type="pc",
                entity_label="PC1",
                damage_results=[_dmg_result(opp.pk)],
                participant_id=pc1.pk,
                effect_type_id=EffectTypeFactory().pk,
            ),
            ActionOutcome(
                entity_type="pc",
                entity_label="PC1",
                damage_results=[_dmg_result(opp.pk)],
                participant_id=pc1.pk,
                effect_type_id=EffectTypeFactory().pk,
            ),
        ]
        assess_break_bar(encounter, outcomes)
        opp.refresh_from_db()
        # Pre-#2642: the old per-actor gate (>=2 distinct PCs) blocked a solo
        # PC entirely — no chip. Post-#2642 the per-actor CAP is gone (ruled
        # dead): PC1 still only counts once as an (actor, DAMAGE) pair (1
        # base unit — repeats of the same actor+kind don't stack), but each
        # of PC1's two distinct effect_types is a novel (DAMAGE, effect_type)
        # pair this encounter (+2). 1 + 2 = 3; 5-3=2.
        self.assertEqual(opp.break_bar_current, 2)

    def test_already_vulnerable_does_not_assess(self):
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            break_bar_threshold=10,
            break_bar_current=10,
            vulnerability_rounds=2,
            vulnerability_rounds_remaining=2,
        )
        combo = ComboDefinitionFactory(bonus_damage=15)
        outcome = ActionOutcome(
            entity_type="pc",
            entity_label="PC1",
            combo_used=combo,
            damage_results=[_dmg_result(opp.pk)],
            participant_id=1,
            effect_type_id=1,
        )
        assess_break_bar(encounter, [outcome])
        opp.refresh_from_db()
        self.assertEqual(opp.break_bar_current, 10)  # unchanged — already vulnerable


class BreakBarContributionPersistenceTests(TestCase):
    """Contributions are persisted per feed kind, replacing the old ephemeral sets."""

    def test_combo_and_damage_rows_persisted_with_kind(self):
        encounter = CombatEncounterFactory()
        opp = BossOpponentFactory(
            encounter=encounter,
            break_bar_threshold=100,
            break_bar_current=100,
            vulnerability_rounds=2,
        )
        combo = ComboDefinitionFactory(bonus_damage=5)
        effect_type = EffectTypeFactory()
        participant = CombatParticipantFactory(encounter=encounter)
        outcome = ActionOutcome(
            entity_type="pc",
            entity_label="PC1",
            combo_used=combo,
            damage_results=[_dmg_result(opp.pk)],
            participant_id=participant.pk,
            effect_type_id=effect_type.pk,
        )
        assess_break_bar(encounter, [outcome])

        kinds = set(
            BreakBarContribution.objects.filter(opponent=opp).values_list("kind", flat=True)
        )
        self.assertEqual(kinds, {BreakContributionKind.COMBO, BreakContributionKind.DAMAGE})
        for row in BreakBarContribution.objects.filter(opponent=opp):
            self.assertEqual(row.participant_id, participant.pk)
            self.assertEqual(row.effect_type_id, effect_type.pk)

    def test_novelty_doubles_only_on_first_occurrence_per_encounter(self):
        encounter = CombatEncounterFactory(round_number=1)
        opp = BossOpponentFactory(
            encounter=encounter,
            break_bar_threshold=100,
            break_bar_current=100,
            vulnerability_rounds=2,
        )
        outcome = ActionOutcome(
            entity_type="pc",
            entity_label="PC1",
            damage_results=[_dmg_result(opp.pk)],
            participant_id=CombatParticipantFactory(encounter=encounter).pk,
            effect_type_id=EffectTypeFactory().pk,
        )

        # Round 1: 1 base unit + 1 novelty bonus (first (DAMAGE, 10) this encounter) = 2.
        assess_break_bar(encounter, [outcome])
        opp.refresh_from_db()
        self.assertEqual(opp.break_bar_current, 98)

        # Round 2: same actor, same effect_type — no longer novel. 1 base unit only.
        encounter.round_number = 2
        assess_break_bar(encounter, [outcome])
        opp.refresh_from_db()
        self.assertEqual(opp.break_bar_current, 97)


class BreakBarLieutenantGateTests(TestCase):
    """Proportional lieutenant gate: 1 / (1 + active_unsuppressed_reinforcers)."""

    def _boss_and_raw_six_outcomes(self, encounter):
        opp = BossOpponentFactory(
            encounter=encounter,
            break_bar_threshold=1000,
            break_bar_current=1000,
            vulnerability_rounds=2,
        )
        outcomes = [
            ActionOutcome(
                entity_type="pc",
                entity_label=f"PC{i}",
                damage_results=[_dmg_result(opp.pk)],
                participant_id=CombatParticipantFactory(encounter=encounter).pk,
                effect_type_id=EffectTypeFactory().pk,
            )
            for i in (1, 2, 3)
        ]
        # 3 distinct (actor, DAMAGE) pairs (base=3) + 3 novel (DAMAGE, effect_type)
        # pairs (bonus=3) = 6 raw units, ungated.
        return opp, outcomes

    def test_two_active_lieutenants_gate_to_one_third_rate(self):
        encounter = CombatEncounterFactory(round_number=1)
        opp, outcomes = self._boss_and_raw_six_outcomes(encounter)
        for _ in range(2):
            lieutenant = CombatOpponentFactory(encounter=encounter, reinforces=opp)
            CombatOpponentActionFactory(opponent=lieutenant, round_number=1)

        self.assertEqual(_active_reinforcer_count(opp, 1), 2)
        assess_break_bar(encounter, outcomes)
        opp.refresh_from_db()
        self.assertEqual(opp.break_bar_current, 1000 - (6 // 3))  # divisor 1+2=3

    def test_suppressed_lieutenant_restores_rate(self):
        encounter = CombatEncounterFactory(round_number=1)
        opp, outcomes = self._boss_and_raw_six_outcomes(encounter)
        active_lt = CombatOpponentFactory(encounter=encounter, reinforces=opp)
        CombatOpponentActionFactory(opponent=active_lt, round_number=1)
        suppressed_lt = CombatOpponentFactory(encounter=encounter, reinforces=opp)
        CombatOpponentActionFactory(opponent=suppressed_lt, round_number=1)
        control_category = ConditionCategoryFactory(alters_behavior=True)
        control_condition = ConditionTemplateFactory(category=control_category)
        ConditionInstanceFactory(target=suppressed_lt.objectdb, condition=control_condition)

        # The suppressed lieutenant's behavior-altering condition excludes it
        # from the gate — only 1 active reinforcer remains.
        self.assertEqual(_active_reinforcer_count(opp, 1), 1)
        assess_break_bar(encounter, outcomes)
        opp.refresh_from_db()
        self.assertEqual(opp.break_bar_current, 1000 - (6 // 2))  # divisor 1+1=2

    def test_idle_lieutenant_does_not_gate(self):
        encounter = CombatEncounterFactory(round_number=1)
        opp, outcomes = self._boss_and_raw_six_outcomes(encounter)
        active_lt = CombatOpponentFactory(encounter=encounter, reinforces=opp)
        CombatOpponentActionFactory(opponent=active_lt, round_number=1)
        # Parked/idle: reinforces the boss but has no CombatOpponentAction this round.
        CombatOpponentFactory(encounter=encounter, reinforces=opp)

        self.assertEqual(_active_reinforcer_count(opp, 1), 1)
        assess_break_bar(encounter, outcomes)
        opp.refresh_from_db()
        self.assertEqual(opp.break_bar_current, 1000 - (6 // 2))  # divisor 1+1=2, idle excluded


class BreakBarHoldFeedTests(TestCase):
    """HOLD feed: a PC-side LOCK-clash win against the boss this round."""

    def test_pc_lock_win_this_round_credits_hold(self):
        encounter = CombatEncounterFactory(round_number=3)
        opp = BossOpponentFactory(
            encounter=encounter,
            break_bar_threshold=100,
            break_bar_current=100,
            vulnerability_rounds=2,
        )
        participant = CombatParticipantFactory(encounter=encounter)
        clash = LockClashFactory(
            encounter=encounter,
            npc_opponent=opp,
            resolved_round=3,
            resolution=ClashResolution.PC_DECISIVE,
        )
        clash_round = ClashRoundFactory(clash=clash, round_number=3)
        ClashContributionFactory(
            clash_round=clash_round,
            character=participant.character_sheet,
        )

        assess_break_bar(encounter, [])

        hold_rows = BreakBarContribution.objects.filter(
            opponent=opp, kind=BreakContributionKind.HOLD
        )
        self.assertEqual(hold_rows.count(), 1)
        self.assertEqual(hold_rows.first().participant_id, participant.pk)
        opp.refresh_from_db()
        # 1 base unit + 1 novelty bonus (first (HOLD, None) pair this encounter) = 2.
        self.assertEqual(opp.break_bar_current, 98)


class BreakBarPacingFloorTests(TestCase):
    """minimum_break_bar_threshold clamps to (soulfray_stages + 2) * BAR_UNITS_PER_ROUND."""

    def test_no_soulfray_stages_authored_returns_zero(self):
        self.assertEqual(minimum_break_bar_threshold(), 0)

    def test_authored_soulfray_stages_set_the_floor(self):
        soulfray = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME, has_progression=True)
        ConditionStageFactory.create_batch(3, condition=soulfray)
        # (3 + 2) * BAR_UNITS_PER_ROUND(=2) = 10.
        self.assertEqual(minimum_break_bar_threshold(), 10)


class BreakBarCelebrationTests(TestCase):
    """The break broadcast names every distinct contributor this encounter."""

    def test_celebration_names_all_contributors(self):
        encounter = CombatEncounterFactory()
        opp = BossOpponentFactory(
            encounter=encounter,
            break_bar_threshold=2,
            break_bar_current=2,
            vulnerability_rounds=2,
        )
        p1 = CombatParticipantFactory(encounter=encounter)
        p2 = CombatParticipantFactory(encounter=encounter)
        outcomes = [
            ActionOutcome(
                entity_type="pc",
                entity_label="PC1",
                damage_results=[_dmg_result(opp.pk)],
                participant_id=p1.pk,
                effect_type_id=EffectTypeFactory().pk,
            ),
            ActionOutcome(
                entity_type="pc",
                entity_label="PC2",
                damage_results=[_dmg_result(opp.pk)],
                participant_id=p2.pk,
                effect_type_id=EffectTypeFactory().pk,
            ),
        ]

        assess_break_bar(encounter, outcomes)
        opp.refresh_from_db()
        self.assertEqual(opp.break_bar_current, 0)
        self.assertGreater(opp.vulnerability_rounds_remaining, 0)

        narration = Interaction.objects.filter(
            scene=encounter.scene, mode=InteractionMode.OUTCOME
        ).latest("timestamp")
        self.assertIn(str(p1), narration.content)
        self.assertIn(str(p2), narration.content)


class BreakBarDebuffAndSuppressionFeedTests(TestCase):
    """DEBUFF (boss) and SUPPRESSION (lieutenant) feeds, round-scoped by applied_at."""

    def test_new_behavior_altering_condition_on_boss_credits_debuff(self):
        encounter = CombatEncounterFactory(round_started_at=timezone.now() - timedelta(seconds=5))
        opp = BossOpponentFactory(
            encounter=encounter,
            break_bar_threshold=100,
            break_bar_current=100,
            vulnerability_rounds=2,
        )
        control_category = ConditionCategoryFactory(alters_behavior=True)
        control_condition = ConditionTemplateFactory(category=control_category)
        ConditionInstanceFactory(target=opp.objectdb, condition=control_condition)

        assess_break_bar(encounter, [])

        self.assertTrue(
            BreakBarContribution.objects.filter(
                opponent=opp, kind=BreakContributionKind.DEBUFF
            ).exists()
        )
        opp.refresh_from_db()
        self.assertLess(opp.break_bar_current, 100)

    def test_lieutenant_newly_suppressed_by_lock_credits_suppression(self):
        encounter = CombatEncounterFactory(round_number=2)
        opp = BossOpponentFactory(
            encounter=encounter,
            break_bar_threshold=100,
            break_bar_current=100,
            vulnerability_rounds=2,
        )
        lieutenant = CombatOpponentFactory(encounter=encounter, reinforces=opp)
        participant = CombatParticipantFactory(encounter=encounter)
        EngagementLockFactory(
            encounter=encounter,
            opponent=lieutenant,
            participant=participant,
            started_round=2,
        )

        assess_break_bar(encounter, [])

        suppression_rows = BreakBarContribution.objects.filter(
            opponent=opp, kind=BreakContributionKind.SUPPRESSION
        )
        self.assertEqual(suppression_rows.count(), 1)
        self.assertEqual(suppression_rows.first().participant_id, participant.pk)
