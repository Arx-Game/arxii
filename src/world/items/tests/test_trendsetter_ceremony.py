"""Tests for the seasonal trendsetter ceremony + cron registration (#514).

The ceremony reads a society's accumulated ``FacetVogueMomentum``, crowns the
highest-acclaim presenter's primary persona as the season's Trendsetter, and
rewrites the society's living FashionStyle so its in-vogue facets are the
top-N momentum facets.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import (
    FASHION_LIVING_STYLE_NAME_TEMPLATE,
    FASHION_PRESENTATION_MODIFIER_TARGET_NAME,
    FASHION_TREND_FACET_COUNT,
)
from world.items.factories import (
    FacetVogueMomentumFactory,
    FashionPresentationFactory,
)
from world.items.models import FashionStyleBonus, Trendsetter
from world.items.services.trendsetter import (
    run_all_trendsetter_ceremonies,
    run_trendsetter_ceremony,
)
from world.magic.factories import FacetFactory
from world.mechanics.factories import ModifierTargetFactory
from world.societies.factories import SocietyFactory


class TrendsetterCeremonyTests(TestCase):
    """The ceremony crowns, rewrites the living style, and (best-effort) buffs."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.society = SocietyFactory()
        # Four facets with descending momentum so the top-N is deterministic.
        cls.facets = [FacetFactory() for _ in range(4)]
        for points, facet in zip([40, 30, 20, 10], cls.facets, strict=True):
            FacetVogueMomentumFactory(society=cls.society, facet=facet, points=points)

        # Two presenters; the first wins on summed acclaim.
        cls.winner = CharacterSheetFactory()
        cls.loser = CharacterSheetFactory()
        FashionPresentationFactory(
            presenter=cls.winner,
            perceiving_society=cls.society,
            acclaim=50,
        )
        FashionPresentationFactory(
            presenter=cls.winner,
            perceiving_society=cls.society,
            acclaim=10,
        )
        FashionPresentationFactory(
            presenter=cls.loser,
            perceiving_society=cls.society,
            acclaim=30,
        )

    def test_crowns_top_acclaim_presenter_and_rewrites_living_style(self) -> None:
        # Author the fashion ModifierTarget so the bonus path runs.
        ModifierTargetFactory(name=FASHION_PRESENTATION_MODIFIER_TARGET_NAME)

        trendsetter = run_trendsetter_ceremony(self.society)

        self.assertIsNotNone(trendsetter)
        assert trendsetter is not None
        self.assertEqual(trendsetter.persona, self.winner.primary_persona)
        self.assertEqual(trendsetter.society, self.society)

        # A Trendsetter row was recorded.
        self.assertEqual(Trendsetter.objects.count(), 1)

        # The society now points at a living style whose in-vogue facets are the
        # top-N momentum facets.
        self.society.refresh_from_db()
        style = self.society.current_fashion_style
        self.assertIsNotNone(style)
        assert style is not None
        self.assertEqual(
            style.name,
            FASHION_LIVING_STYLE_NAME_TEMPLATE.format(society=self.society.name),
        )
        expected_facets = set(self.facets[:FASHION_TREND_FACET_COUNT])
        self.assertEqual(set(style.in_vogue_facets.all()), expected_facets)
        self.assertEqual(trendsetter.fashion_style, style)

        # A bonus was created since the ModifierTarget exists.
        self.assertTrue(FashionStyleBonus.objects.filter(fashion_style=style).exists())

    def test_no_momentum_returns_none_and_leaves_style_unchanged(self) -> None:
        empty_society = SocietyFactory()
        result = run_trendsetter_ceremony(empty_society)
        self.assertIsNone(result)
        self.assertEqual(Trendsetter.objects.filter(society=empty_society).count(), 0)
        empty_society.refresh_from_db()
        self.assertIsNone(empty_society.current_fashion_style)

    def test_unauthored_modifier_target_still_crowns_without_bonus(self) -> None:
        # No ModifierTarget authored -> no crash, no bonus, but still crowns.
        trendsetter = run_trendsetter_ceremony(self.society)
        self.assertIsNotNone(trendsetter)
        assert trendsetter is not None
        self.society.refresh_from_db()
        style = self.society.current_fashion_style
        self.assertIsNotNone(style)
        assert style is not None
        self.assertEqual(
            set(style.in_vogue_facets.all()),
            set(self.facets[:FASHION_TREND_FACET_COUNT]),
        )
        self.assertFalse(FashionStyleBonus.objects.filter(fashion_style=style).exists())

    def test_no_presentations_returns_none(self) -> None:
        # Momentum but no presentations -> nobody to crown.
        society = SocietyFactory()
        FacetVogueMomentumFactory(society=society, facet=FacetFactory(), points=15)
        result = run_trendsetter_ceremony(society)
        self.assertIsNone(result)
        self.assertEqual(Trendsetter.objects.filter(society=society).count(), 0)

    def test_run_all_only_touches_societies_with_positive_momentum(self) -> None:
        # A second society with momentum + a presenter.
        other = SocietyFactory()
        other_facet = FacetFactory()
        FacetVogueMomentumFactory(society=other, facet=other_facet, points=5)
        presenter = CharacterSheetFactory()
        FashionPresentationFactory(
            presenter=presenter,
            perceiving_society=other,
            acclaim=7,
        )
        # A third society with NO momentum is ignored.
        SocietyFactory()

        results = run_all_trendsetter_ceremonies()
        crowned_societies = {t.society for t in results}
        self.assertEqual(crowned_societies, {self.society, other})


class TrendsetterCronRegistrationTests(TestCase):
    """The fashion cron tasks register through items.tasks.register_all_tasks."""

    def setUp(self) -> None:
        from world.game_clock.task_registry import clear_registry

        clear_registry()

    def tearDown(self) -> None:
        from world.game_clock.task_registry import clear_registry

        clear_registry()

    def test_fashion_tasks_registered(self) -> None:
        from world.game_clock.task_registry import get_registered_tasks
        from world.items.tasks import register_all_tasks

        register_all_tasks()
        keys = {t.task_key for t in get_registered_tasks()}
        self.assertIn("fashion.trendsetter_ceremony", keys)
        self.assertIn("fashion.vogue_momentum_decay", keys)

    def test_game_clock_aggregator_registers_fashion_tasks(self) -> None:
        from world.game_clock.task_registry import get_registered_tasks
        from world.game_clock.tasks import register_all_tasks

        register_all_tasks()
        keys = {t.task_key for t in get_registered_tasks()}
        self.assertIn("fashion.trendsetter_ceremony", keys)
        self.assertIn("fashion.vogue_momentum_decay", keys)
