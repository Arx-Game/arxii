"""Tests for decay_all_conditions_tick (Scope 6 §5.4).

Scheduler entry point. Iterates ConditionInstance rows with resolved_at
NULL and opt-in (passive_decay_per_day > 0). Honors
passive_decay_blocked_in_engagement and passive_decay_max_severity.
"""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import decay_all_conditions_tick
from world.mechanics.factories import CharacterEngagementFactory


class DecayAllConditionsTickTests(TestCase):
    def test_only_opt_in_subset_ticks(self):
        opt_in = ConditionTemplateFactory(passive_decay_per_day=1)
        opt_in_stage = ConditionStageFactory(condition=opt_in, severity_threshold=1)
        opt_out = ConditionTemplateFactory(passive_decay_per_day=0)
        opt_out_stage = ConditionStageFactory(condition=opt_out, severity_threshold=1)

        inst_in = ConditionInstanceFactory(
            condition=opt_in,
            current_stage=opt_in_stage,
            severity=3,
        )
        inst_out = ConditionInstanceFactory(
            condition=opt_out,
            current_stage=opt_out_stage,
            severity=3,
        )

        summary = decay_all_conditions_tick()
        inst_in.refresh_from_db()
        inst_out.refresh_from_db()

        self.assertEqual(inst_in.severity, 2)
        self.assertEqual(inst_out.severity, 3)
        self.assertEqual(summary.ticked, 1)
        self.assertEqual(summary.examined, 1)

    def test_engagement_gate_honored_when_flag_true(self):
        template = ConditionTemplateFactory(
            passive_decay_per_day=1,
            passive_decay_blocked_in_engagement=True,
        )
        stage = ConditionStageFactory(condition=template, severity_threshold=1)

        engagement = CharacterEngagementFactory()
        target = engagement.character

        inst = ConditionInstanceFactory(
            target=target,
            condition=template,
            current_stage=stage,
            severity=3,
        )

        summary = decay_all_conditions_tick()
        inst.refresh_from_db()

        self.assertEqual(inst.severity, 3)
        self.assertEqual(summary.ticked, 0)
        self.assertEqual(summary.engagement_blocked, 1)
        self.assertEqual(summary.examined, 1)

    def test_positive_decays_when_passive_decay_blocked_in_engagement_is_false(self):
        template = ConditionTemplateFactory(
            passive_decay_per_day=1,
            passive_decay_blocked_in_engagement=False,
        )
        stage = ConditionStageFactory(condition=template, severity_threshold=1)

        engagement = CharacterEngagementFactory()
        target = engagement.character

        inst = ConditionInstanceFactory(
            target=target,
            condition=template,
            current_stage=stage,
            severity=3,
        )

        summary = decay_all_conditions_tick()
        inst.refresh_from_db()

        self.assertEqual(inst.severity, 2)
        self.assertEqual(summary.ticked, 1)
        self.assertEqual(summary.engagement_blocked, 0)
        self.assertEqual(summary.examined, 1)

    def test_passive_decay_max_severity_gates_soulfray_stage2_plus(self):
        template = ConditionTemplateFactory(
            passive_decay_per_day=1,
            passive_decay_max_severity=5,
        )
        stage = ConditionStageFactory(condition=template, severity_threshold=1)

        inst = ConditionInstanceFactory(
            condition=template,
            current_stage=stage,
            severity=6,
        )

        summary = decay_all_conditions_tick()
        inst.refresh_from_db()

        self.assertEqual(inst.severity, 6)
        self.assertEqual(summary.ticked, 0)
        self.assertEqual(summary.severity_gated, 1)
        self.assertEqual(summary.examined, 1)

    def test_non_character_target_never_engagement_gated(self):
        template = ConditionTemplateFactory(
            passive_decay_per_day=1,
            passive_decay_blocked_in_engagement=True,
        )
        stage = ConditionStageFactory(condition=template, severity_threshold=1)

        room = ObjectDB.objects.create(
            db_key="AnchorRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        inst = ConditionInstanceFactory(
            target=room,
            condition=template,
            current_stage=stage,
            severity=3,
        )

        summary = decay_all_conditions_tick()
        inst.refresh_from_db()

        self.assertEqual(inst.severity, 2)
        self.assertEqual(summary.ticked, 1)
        self.assertEqual(summary.engagement_blocked, 0)
        self.assertEqual(summary.examined, 1)

    def test_n_instances_bounded_query_count(self):
        """Query count grows linearly with instances, not exponentially.

        With 10 instances the cost is 1 outer SELECT + 5 queries per instance
        (engagement check, stage lookup, savepoint, update, release savepoint) =
        51 queries. This is acceptable for a daily scheduler tick — not a hot
        path. The key assertion is linearity: doubling instances should not
        more than double queries.
        """
        template = ConditionTemplateFactory(passive_decay_per_day=1)
        stage = ConditionStageFactory(condition=template, severity_threshold=1)
        for _ in range(10):
            ConditionInstanceFactory(
                condition=template,
                current_stage=stage,
                severity=3,
            )

        with self.assertNumQueries(51):
            summary = decay_all_conditions_tick()

        self.assertEqual(summary.ticked, 10)
        self.assertEqual(summary.examined, 10)
