"""soulfray_ladder_summary(): each Soulfray stage as the resilience roll sees it (#4089)."""

from __future__ import annotations

from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.checks.factories import ConsequenceFactory
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.services.soulfray import (
    is_soulfray_stage,
    soulfray_ladder_summary,
    soulfray_stages,
)
from world.traits.factories import CheckOutcomeFactory


class SoulfrayLadderSummaryTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME, has_progression=True)
        other = ConditionTemplateFactory(name="Not Soulfray", has_progression=True)
        failure = CheckOutcomeFactory(name="Failure", success_level=-1)
        botch = CheckOutcomeFactory(name="Critical Failure", success_level=-3)
        cls.common = ConsequencePoolFactory(name="Soulfray - common")
        cls.shared = ConsequenceFactory(outcome_tier=failure, label="PLACEHOLDER ringing ears")
        ConsequencePoolEntryFactory(pool=cls.common, consequence=cls.shared)
        cls.tearing_pool = ConsequencePoolFactory(name="Soulfray - Tearing", parent=cls.common)
        cls.wound = ConsequenceFactory(outcome_tier=botch, label="PLACEHOLDER wound", weight=2)
        ConsequencePoolEntryFactory(pool=cls.tearing_pool, consequence=cls.wound)
        cls.fraying = ConditionStageFactory(
            condition=cls.template, stage_order=1, name="Fraying", severity_threshold=1
        )
        cls.tearing = ConditionStageFactory(
            condition=cls.template,
            stage_order=2,
            name="Tearing",
            severity_threshold=6,
            consequence_pool=cls.tearing_pool,
        )
        cls.elsewhere = ConditionStageFactory(condition=other, stage_order=1, name="Elsewhere")

    def test_one_summary_per_soulfray_stage_in_order(self) -> None:
        names = [summary.stage.name for summary in soulfray_ladder_summary()]
        self.assertEqual(names, ["Fraying", "Tearing"])

    def test_soulfray_stages_and_is_soulfray_stage_agree(self) -> None:
        self.assertEqual(list(soulfray_stages()), [self.fraying, self.tearing])
        self.assertTrue(is_soulfray_stage(self.tearing))
        self.assertFalse(is_soulfray_stage(self.elsewhere))

    def test_a_stage_with_no_pool_has_no_consequences(self) -> None:
        fraying = soulfray_ladder_summary()[0]
        self.assertIsNone(fraying.pool)
        self.assertEqual(fraying.consequence_count, 0)
        self.assertFalse(fraying.can_kill)

    def test_a_child_pool_merges_its_parent_and_marks_those_rows_shared(self) -> None:
        tearing = soulfray_ladder_summary()[1]
        self.assertEqual(tearing.consequence_count, 2)
        self.assertEqual(tearing.shared_consequence_ids, frozenset({self.shared.pk}))

    def test_a_child_exclusion_drops_the_parent_row(self) -> None:
        ConsequencePoolEntryFactory(
            pool=self.tearing_pool, consequence=self.shared, is_excluded=True
        )
        tearing = soulfray_ladder_summary()[1]
        self.assertEqual([wc.consequence for wc in tearing.consequences], [self.wound])
        self.assertEqual(tearing.shared_consequence_ids, frozenset())

    def test_an_inherited_lethal_row_makes_the_stage_able_to_kill(self) -> None:
        lethal = ConsequenceFactory(label="PLACEHOLDER death", character_loss=True)
        ConsequencePoolEntryFactory(pool=self.common, consequence=lethal)
        self.assertTrue(soulfray_ladder_summary()[1].can_kill)

    def test_a_pooled_ladder_costs_two_queries(self) -> None:
        with self.assertNumQueries(2):
            soulfray_ladder_summary()
