"""soulfray_ladder_summary(): each Soulfray stage as the resilience roll sees it (#4089)."""

from __future__ import annotations

from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from actions.types import WeightedConsequence
from evennia_extensions.factories import CharacterFactory
from world.checks.factories import ConsequenceFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionStage
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.services.soulfray import (
    get_soulfray_warning,
    is_soulfray_stage,
    nonlethal_ceiling_for,
    nonlethal_severity_ceiling,
    soulfray_ladder_summary,
    soulfray_stages,
)
from world.magic.types import SoulfrayStageSummary
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


class InheritedDeathRiskTests(TestCase):
    """A lethal row inherited from the parent pool caps and warns like an own row."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME, has_progression=True)
        cls.common = ConsequencePoolFactory(name="Soulfray - common")
        cls.lethal = ConsequenceFactory(label="PLACEHOLDER death", character_loss=True)
        ConsequencePoolEntryFactory(pool=cls.common, consequence=cls.lethal)
        cls.child = ConsequencePoolFactory(name="Soulfray - Unravelling", parent=cls.common)
        ConditionStageFactory(
            condition=cls.template, stage_order=1, name="Fraying", severity_threshold=1
        )
        cls.unravelling = ConditionStageFactory(
            condition=cls.template,
            stage_order=5,
            name="Unravelling",
            severity_threshold=66,
            consequence_pool=cls.child,
        )

    def test_ceiling_counts_a_lethal_row_inherited_from_the_parent(self) -> None:
        self.assertEqual(nonlethal_severity_ceiling(), 65)

    def test_ceiling_ignores_a_lethal_row_the_stage_excludes(self) -> None:
        ConsequencePoolEntryFactory(pool=self.child, consequence=self.lethal, is_excluded=True)
        self.assertIsNone(nonlethal_severity_ceiling())

    def test_checkpoint_warns_of_an_inherited_death_risk(self) -> None:
        character = CharacterFactory()
        ConditionInstanceFactory(
            target=character, condition=self.template, current_stage=self.unravelling
        )
        warning = get_soulfray_warning(character)
        self.assertIsNotNone(warning)
        self.assertTrue(warning.has_death_risk)

    def test_a_time_based_lethal_stage_never_sets_the_cap(self) -> None:
        """A time-based stage never caps — even when IT also carries a lethal row (#4089 P5).

        Without the ``severity_threshold is not None`` guard, a buggy
        ``nonlethal_ceiling_for`` either crashes comparing ``None`` against an int, or
        (a filter-then-default-0 variant) drags the cap down to 0 — both wrong. The only
        correct answer is the severity-based stage's own threshold minus one: the
        time-based stage is invisible to the cap computation.
        """
        lethal = ConsequenceFactory(label="PLACEHOLDER timed death", character_loss=True)
        timed_stage = ConditionStage(name="Timed", stage_order=9, severity_threshold=None)
        timed_summary = SoulfrayStageSummary(
            stage=timed_stage,
            pool=None,
            consequences=(WeightedConsequence(consequence=lethal, weight=1, character_loss=True),),
            shared_consequence_ids=frozenset(),
        )
        severity_stage = ConditionStage(name="Severity", stage_order=10, severity_threshold=66)
        severity_summary = SoulfrayStageSummary(
            stage=severity_stage,
            pool=None,
            consequences=(WeightedConsequence(consequence=lethal, weight=1, character_loss=True),),
            shared_consequence_ids=frozenset(),
        )
        self.assertEqual(nonlethal_ceiling_for([timed_summary, severity_summary]), 65)
