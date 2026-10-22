"""draws_aggro conditions steer enemy target selection (#4572)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import ObjectDBFactory
from world.combat.constants import (
    EncounterType,
    EngagementLockStatus,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EngagementLockFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
    ThreatRecordFactory,
)
from world.combat.models import ThreatRecord
from world.combat.services import select_npc_actions
from world.conditions.constants import DurationType
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.services import (
    aggro_priority_by_target,
    draws_aggro_target_ids,
    turn_order_modifier_by_target,
)
from world.scenes.constants import RoundStatus


class ConditionTotalsByTargetTests(TestCase):
    """The batched helpers sum flagged, active conditions per target in one query."""

    @classmethod
    def setUpTestData(cls):
        cls.alpha = ObjectDBFactory(db_key="Alpha4572")
        cls.beta = ObjectDBFactory(db_key="Beta4572")
        cls.bystander = ObjectDBFactory(db_key="Bystander4572")
        cls.taunt = ConditionTemplateFactory(name="Taunt 4572", draws_aggro=True, aggro_priority=10)
        cls.beacon = ConditionTemplateFactory(
            name="Beacon 4572", draws_aggro=True, aggro_priority=5
        )
        cls.unflagged_priority = ConditionTemplateFactory(
            name="Unflagged Priority 4572", draws_aggro=False, aggro_priority=99
        )
        cls.haste = ConditionTemplateFactory(
            name="Haste 4572", affects_turn_order=True, turn_order_modifier=5
        )
        cls.slow = ConditionTemplateFactory(
            name="Slow 4572", affects_turn_order=True, turn_order_modifier=-3
        )
        cls.unflagged_modifier = ConditionTemplateFactory(
            name="Unflagged Modifier 4572", affects_turn_order=False, turn_order_modifier=40
        )

    def test_aggro_sums_per_target_and_skips_unflagged(self):
        ConditionInstanceFactory(target=self.alpha, condition=self.taunt)
        ConditionInstanceFactory(target=self.alpha, condition=self.beacon)
        ConditionInstanceFactory(target=self.alpha, condition=self.unflagged_priority)
        ConditionInstanceFactory(target=self.beta, condition=self.beacon)

        with self.assertNumQueries(1):
            result = aggro_priority_by_target([self.alpha, self.beta, self.bystander])

        self.assertEqual(result, {self.alpha.pk: 15, self.beta.pk: 5})

    def test_suppressed_aggro_is_skipped(self):
        ConditionInstanceFactory(target=self.alpha, condition=self.taunt, is_suppressed=True)

        self.assertEqual(aggro_priority_by_target([self.alpha]), {})

    def test_expired_ingame_time_aggro_is_skipped(self):
        timed = ConditionTemplateFactory(
            name="Timed Taunt 4572",
            draws_aggro=True,
            aggro_priority=7,
            default_duration_type=DurationType.INGAME_TIME,
        )
        ConditionInstanceFactory(
            target=self.alpha, condition=timed, expires_at=timezone.now() - timedelta(hours=1)
        )
        ConditionInstanceFactory(
            target=self.beta, condition=timed, expires_at=timezone.now() + timedelta(hours=1)
        )

        self.assertEqual(aggro_priority_by_target([self.alpha, self.beta]), {self.beta.pk: 7})

    def test_turn_order_modifier_sums_signed_totals(self):
        ConditionInstanceFactory(target=self.alpha, condition=self.haste)
        ConditionInstanceFactory(target=self.alpha, condition=self.slow)
        ConditionInstanceFactory(target=self.alpha, condition=self.unflagged_modifier)
        ConditionInstanceFactory(target=self.beta, condition=self.slow)

        with self.assertNumQueries(1):
            result = turn_order_modifier_by_target([self.alpha, self.beta, self.bystander])

        self.assertEqual(result, {self.alpha.pk: 2, self.beta.pk: -3})

    def test_turn_order_total_of_zero_is_omitted(self):
        zero_sum = ConditionTemplateFactory(
            name="Cancelling Slow 4572", affects_turn_order=True, turn_order_modifier=-5
        )
        ConditionInstanceFactory(target=self.alpha, condition=self.haste)
        ConditionInstanceFactory(target=self.alpha, condition=zero_sum)

        self.assertEqual(turn_order_modifier_by_target([self.alpha]), {})

    def test_draws_aggro_membership_ignores_a_zero_priority(self):
        zero = ConditionTemplateFactory(name="Zero Taunt 4572", draws_aggro=True, aggro_priority=0)
        ConditionInstanceFactory(target=self.alpha, condition=zero)
        ConditionInstanceFactory(target=self.beta, condition=self.unflagged_priority)

        with self.assertNumQueries(1):
            members = draws_aggro_target_ids([self.alpha, self.beta, self.bystander])

        self.assertEqual(members, {self.alpha.pk})
        self.assertEqual(aggro_priority_by_target([self.alpha]), {})

    def test_no_targets_runs_no_query(self):
        with self.assertNumQueries(0):
            self.assertEqual(draws_aggro_target_ids([]), set())
            self.assertEqual(aggro_priority_by_target([]), {})
            self.assertEqual(turn_order_modifier_by_target([]), {})


class AggroTargetingTests(TestCase):
    """select_npc_actions reads draws_aggro conditions beside ThreatRecord."""

    @classmethod
    def setUpTestData(cls):
        cls.taunt = ConditionTemplateFactory(
            name="Targeting Taunt 4572", draws_aggro=True, aggro_priority=60
        )

    def _encounter(self, selection):
        enc = CombatEncounterFactory(
            encounter_type=EncounterType.PARTY_COMBAT,
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(
            pool=pool,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=selection,
            weight=10,
        )
        opp = CombatOpponentFactory(encounter=enc, threat_pool=pool)
        return enc, opp

    def _give_aggro(self, participant, condition=None):
        ConditionInstanceFactory(
            target=participant.character_sheet.character, condition=condition or self.taunt
        )

    def test_highest_threat_prefers_aggro_bearer_when_aggro_outweighs(self):
        enc, opp = self._encounter(TargetSelection.HIGHEST_THREAT)
        high_threat = CombatParticipantFactory(encounter=enc)
        bearer = CombatParticipantFactory(encounter=enc)
        ThreatRecordFactory(encounter=enc, opponent=opp, participant=high_threat, threat_value=50)
        ThreatRecordFactory(encounter=enc, opponent=opp, participant=bearer, threat_value=10)
        self._give_aggro(bearer)

        actions = select_npc_actions(enc)

        self.assertEqual(list(actions[0].targets.all()), [bearer])

    def test_highest_threat_keeps_higher_threat_when_aggro_is_smaller(self):
        enc, opp = self._encounter(TargetSelection.HIGHEST_THREAT)
        high_threat = CombatParticipantFactory(encounter=enc)
        bearer = CombatParticipantFactory(encounter=enc)
        ThreatRecordFactory(encounter=enc, opponent=opp, participant=high_threat, threat_value=90)
        ThreatRecordFactory(encounter=enc, opponent=opp, participant=bearer, threat_value=10)
        self._give_aggro(bearer)

        actions = select_npc_actions(enc)

        self.assertEqual(list(actions[0].targets.all()), [high_threat])

    def test_highest_threat_with_no_threat_records_still_sees_aggro(self):
        enc, _opp = self._encounter(TargetSelection.HIGHEST_THREAT)
        CombatParticipantFactory(encounter=enc)
        bearer = CombatParticipantFactory(encounter=enc)
        self._give_aggro(bearer)

        actions = select_npc_actions(enc)

        self.assertEqual(list(actions[0].targets.all()), [bearer])
        self.assertFalse(ThreatRecord.objects.filter(encounter=enc).exists())

    def test_specific_role_prefers_aggro_bearer_without_shield_role(self):
        enc, _opp = self._encounter(TargetSelection.SPECIFIC_ROLE)
        CombatParticipantFactory(encounter=enc)
        bearer = CombatParticipantFactory(encounter=enc)
        self._give_aggro(bearer)

        actions = select_npc_actions(enc)

        self.assertEqual(list(actions[0].targets.all()), [bearer])

    def test_specific_role_prefers_a_zero_priority_aggro_bearer(self):
        """draws_aggro alone marks the bearer; a priority of 0 adds no threat but still draws."""
        zero = ConditionTemplateFactory(
            name="Zero Priority Taunt 4572", draws_aggro=True, aggro_priority=0
        )
        enc, _opp = self._encounter(TargetSelection.SPECIFIC_ROLE)
        CombatParticipantFactory(encounter=enc)
        bearer = CombatParticipantFactory(encounter=enc)
        self._give_aggro(bearer, zero)

        actions = select_npc_actions(enc)

        self.assertEqual(list(actions[0].targets.all()), [bearer])

    def test_engagement_lock_still_overrides_aggro(self):
        enc, opp = self._encounter(TargetSelection.HIGHEST_THREAT)
        locked = CombatParticipantFactory(encounter=enc)
        bearer = CombatParticipantFactory(encounter=enc)
        self._give_aggro(bearer)
        EngagementLockFactory(
            encounter=enc,
            opponent=opp,
            participant=locked,
            status=EngagementLockStatus.ACTIVE,
        )

        actions = select_npc_actions(enc)

        self.assertEqual(list(actions[0].targets.all()), [locked])
