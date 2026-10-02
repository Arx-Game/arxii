"""The Soulfray Stage Builder's pure reads: ladder, Danger, checks, live lines (#4089)."""

from __future__ import annotations

from django.test import TestCase

from web.admin.soulfray_builder import live
from web.admin.tests.soulfray_ladder import build_ladder, shared_pool, stock
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory
from world.checks.models import Consequence
from world.conditions.factories import ConditionTemplateFactory
from world.magic.factories import AudereMajoraThresholdFactory
from world.magic.services.soulfray import soulfray_ladder_summary


def _summary(name: str):
    return next(s for s in soulfray_ladder_summary() if s.stage.name == name)


class EmptyLadderLiveTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.ladder = build_ladder()

    def test_bars_scale_to_the_top_threshold(self) -> None:
        rows = live.ladder_rows(soulfray_ladder_summary(), self.ladder.stage("Tearing").pk)
        self.assertEqual([row.bar_percent for row in rows], [2, 9, 24, 55, 100])
        self.assertEqual([row.is_open for row in rows], [False, True, False, False, False])

    def test_ladder_line_warns_that_no_stage_can_kill(self) -> None:
        kind, text = live.ladder_line(soulfray_ladder_summary())
        self.assertEqual(kind, "warn")
        self.assertEqual(
            text,
            'No stage can kill yet. The Required-content row "Some Soulfray stage can kill" '
            "stays red.",
        )

    def test_checks_warn_about_the_empty_ladder(self) -> None:
        summaries = soulfray_ladder_summary()
        warns = [
            text
            for kind, text in live.checks(summaries, summaries[1], self.ladder.outcome_list)
            if kind == "warn"
        ]
        self.assertIn(
            "this stage has no consequences; a caster here gains severity and nothing happens.",
            warns,
        )
        self.assertIn("no Soulfray stage can kill. Soulfray is meant to be able to.", warns)
        self.assertIn("5 stages have no consequences yet.", warns)

    def test_danger_has_no_lethal_stage_and_no_cap(self) -> None:
        danger = live.danger(soulfray_ladder_summary(), self.ladder.stage("Tearing"))
        self.assertIsNone(danger.first_lethal)
        self.assertIsNone(danger.nonlethal_cap)
        self.assertEqual(danger.crossing_levels, ())

    def test_table_line_for_an_empty_stage(self) -> None:
        self.assertEqual(
            live.table_line(_summary("Tearing"), self.ladder.outcome_list),
            "No consequences yet: a caster here gains severity and nothing happens.",
        )


class LethalLadderLiveTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.ladder = build_ladder()
        for stage in cls.ladder.stages[:-1]:
            stock(stage, cls.ladder)
        stock(cls.ladder.stage("Unravelling"), cls.ladder, lethal_tier="Critical Failure")
        AudereMajoraThresholdFactory(
            boundary_level=10, minimum_warp_stage=cls.ladder.stage("Sundering")
        )

    def test_danger_names_the_first_lethal_stage_and_the_cap(self) -> None:
        danger = live.danger(soulfray_ladder_summary(), self.ladder.stage("Unravelling"))
        self.assertEqual(danger.first_lethal.stage.name, "Unravelling")
        self.assertEqual(danger.nonlethal_cap, 65)
        self.assertEqual(danger.lethal_stage_names, ("Unravelling",))

    def test_crossings_that_need_the_stage(self) -> None:
        danger = live.danger(soulfray_ladder_summary(), self.ladder.stage("Sundering"))
        self.assertEqual(danger.crossing_levels, (10,))

    def test_kill_odds_by_weight(self) -> None:
        self.assertEqual(
            live.kill_odds(_summary("Unravelling"), self.ladder.outcome_list),
            [
                "Chance a Critical Failure here kills: 1 in 4 by weight. Non-lethal casts "
                "never draw it."
            ],
        )

    def test_ladder_line_states_the_cap(self) -> None:
        self.assertEqual(
            live.ladder_line(soulfray_ladder_summary()),
            (
                "ok",
                "Unravelling can kill. Non-lethal casts stop adding severity at 65, one "
                "short of it.",
            ),
        )

    def test_checks_pass_and_warn_about_the_stage_below_death(self) -> None:
        summaries = soulfray_ladder_summary()
        result = live.checks(summaries, summaries[-1], self.ladder.outcome_list)
        self.assertEqual(
            result,
            [
                ("ok", "every roll result draws something here."),
                ("ok", "a stage can kill (Unravelling)."),
                ("ok", "every stage has consequences."),
                (
                    "warn",
                    "Sundering can be reached by a non-lethal cast and is one stage below a "
                    "death stage. Check its warning text says so.",
                ),
            ],
        )

    def test_stage_counts_and_table_line(self) -> None:
        counts = live.stage_counts(_summary("Unravelling"))
        self.assertEqual((counts.consequences, counts.shared, counts.kill_rows), (6, 0, 1))
        self.assertEqual(
            live.table_line(_summary("Unravelling"), self.ladder.outcome_list),
            "6 consequences reachable here; 1 can kill.",
        )


class SharedPoolLiveTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.ladder = build_ladder()
        common = shared_pool(cls.ladder, ("Partial Success", "Success"))
        stock(
            cls.ladder.stage("Tearing"),
            cls.ladder,
            tiers=("Critical Failure", "Failure"),
            parent=common,
        )
        ConsequenceEffectFactory(
            consequence=Consequence.objects.get(label="Tearing Failure"),
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=ConditionTemplateFactory(name="Shaken"),
            condition_severity=1,
        )

    def test_counts_shared_rows_and_effects(self) -> None:
        counts = live.stage_counts(_summary("Tearing"))
        self.assertEqual((counts.consequences, counts.shared, counts.effects), (4, 2, 1))

    def test_table_line_names_the_result_that_draws_nothing(self) -> None:
        self.assertEqual(
            live.table_line(_summary("Tearing"), self.ladder.outcome_list),
            "4 consequences reachable here; none can kill; Critical Success draws nothing at "
            "this stage.",
        )

    def test_checks_warn_about_the_result_that_draws_nothing(self) -> None:
        summaries = soulfray_ladder_summary()
        result = live.checks(summaries, _summary("Tearing"), self.ladder.outcome_list)
        self.assertEqual(
            result,
            [
                ("ok", "the pool has consequences, so this stage does something."),
                ("warn", "no consequence for Critical Success at this stage."),
                ("warn", "no Soulfray stage can kill. Soulfray is meant to be able to."),
                ("warn", "4 stages have no consequences yet."),
            ],
        )


class SharedStagePoolLiveTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.ladder = build_ladder()
        pool = stock(cls.ladder.stage("Fraying"), cls.ladder)
        tearing = cls.ladder.stage("Tearing")
        tearing.consequence_pool = pool
        tearing.save(update_fields=["consequence_pool"])

    def test_two_stages_on_one_pool_warn(self) -> None:
        summaries = soulfray_ladder_summary()
        result = live.checks(summaries, _summary("Fraying"), self.ladder.outcome_list)
        self.assertIn(
            ("warn", "This pool is also Tearing's pool; an edit here changes that stage too."),
            result,
        )


class TimeBasedStageLiveTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.ladder = build_ladder()
        sundering = cls.ladder.stage("Sundering")
        sundering.severity_threshold = None
        sundering.save(update_fields=["severity_threshold"])
        stock(sundering, cls.ladder, lethal_tier="Critical Failure")

    def test_a_stage_with_no_threshold_has_an_empty_bar_and_sets_no_cap(self) -> None:
        summaries = soulfray_ladder_summary()
        rows = live.ladder_rows(summaries, self.ladder.stage("Fraying").pk)
        self.assertEqual([row.bar_percent for row in rows], [2, 9, 24, 0, 100])
        self.assertIsNone(live.danger(summaries, self.ladder.stage("Sundering")).nonlethal_cap)


class EffectLineTest(TestCase):
    def test_reads_type_target_and_detail(self) -> None:
        effect = ConsequenceEffectFactory(
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=ConditionTemplateFactory(name="Shaken"),
            condition_severity=1,
        )
        self.assertEqual(live.effect_line(effect), "Apply Condition, self, Shaken sev 1")
