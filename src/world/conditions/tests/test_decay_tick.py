"""Tests for decay_all_conditions_tick (Scope 6 §5.4).

Scheduler entry point. Iterates ConditionInstance rows with resolved_at
NULL and opt-in (passive_decay_per_day > 0). Honors
passive_decay_blocked_in_engagement and passive_decay_max_severity.
"""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from evennia_extensions.factories import ObjectDBFactory
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
        target = engagement.character.character

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
        target = engagement.character.character

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

        room = ObjectDBFactory(
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

    def _tick_queries(self, *, add: int, expect_ticked: int) -> int:
        """Add ``add`` decaying instances, run the tick, return queries executed.

        Instances persist across calls within a test, so ``expect_ticked`` is the
        running total — that is what lets two successive calls measure the
        per-instance slope.
        """
        template = ConditionTemplateFactory(passive_decay_per_day=1)
        stage = ConditionStageFactory(condition=template, severity_threshold=1)
        for _ in range(add):
            ConditionInstanceFactory(
                condition=template,
                current_stage=stage,
                severity=3,
            )
        with CaptureQueriesContext(connection) as ctx:
            summary = decay_all_conditions_tick()
        self.assertEqual(summary.ticked, expect_ticked)
        self.assertEqual(summary.examined, expect_ticked)
        return len(ctx)

    def test_n_instances_bounded_query_count(self):
        """Per-instance cost is 4 queries: stage lookup, savepoint, update, release.

        The engagement gate used to add a fifth (one ``CharacterEngagement``
        ``.exists()`` per instance); it is now hoisted into a single batched
        lookup, mirroring ``_apply_ap_regen``'s locked_character_ids set.

        The break-free NPC tick (#2706) adds one constant query (it filters
        for behavior-altering conditions and finds none here).
        """
        self.assertEqual(self._tick_queries(add=10, expect_ticked=10), 43)

    def test_engagement_gate_does_not_scale_with_instance_count(self):
        """The slope is what matters — a reintroduced N+1 would push it to 5.

        Asserting the *difference* between two sizes rather than a single total
        pins the invariant without re-pinning whatever fixed overhead the tick
        happens to carry, so unrelated setup changes don't churn this test.
        """
        ten = self._tick_queries(add=10, expect_ticked=10)
        twenty = self._tick_queries(add=10, expect_ticked=20)
        self.assertEqual(twenty - ten, 4 * 10)
