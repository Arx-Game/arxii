"""Tests for the starting-kit builder on the Techniques panel (#3716).

Pricing itself is the evaluator's job and has its own tests; these patch
`technique_power_eval.evaluate_technique` (and the reference/band helpers) at their
origin with canned reports keyed by technique id, and exercise the kit rules:
option sources, ranking, pick budget, floor, castability, estimates and anchor DE.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from web.admin.tuning import technique_analytics as ta
from world.character_creation.factories import BeginningsFactory, BeginningTraditionFactory
from world.classes.factories import PathFactory
from world.magic.factories import (
    GiftFactory,
    PathGiftGrantFactory,
    TechniqueFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.types.technique_power import (
    FLAG_NOT_CASTABLE_STANDALONE,
    PayloadValuation,
    ReferenceFrame,
    TechniquePowerReport,
    ValuationProvenance,
)
from world.species.factories import SpeciesFactory, SpeciesGiftGrantFactory

_EVALUATE = "web.admin.tuning.technique_analytics.technique_power_eval.evaluate_technique"
_REFERENCE = "web.admin.tuning.technique_analytics.de_valuation.compute_reference_frame"
_BANDS = "web.admin.tuning.technique_analytics.de_valuation.matchup_bands"
_FRAME = ReferenceFrame(outgoing_dpr=1.0, incoming_dpr=1.0, source_label="test")


def _valuation(kind: str, value: float, provenance: ValuationProvenance) -> PayloadValuation:
    return PayloadValuation(kind=kind, label=kind, value=value, provenance=provenance, detail="")


def _report(technique_id: int, name: str, **overrides: Any) -> TechniquePowerReport:
    defaults: dict[str, Any] = {
        "technique_id": technique_id,
        "name": name,
        "gift_name": "Gift",
        "level": 1,
        "tier": 1,
        "category": "Attack",
        "baseline_power": 1,
        "amplified_power": 1,
        "baseline_de": 0.0,
        "amplified_de": 0.0,
        "valuations": (),
        "effective_anima": 1,
        "de_per_anima": 0.0,
        "flags": (),
    }
    defaults.update(overrides)
    return TechniquePowerReport(**defaults)


class StartingKitBuilderTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.beginning = BeginningsFactory()
        cls.tradition = TraditionFactory()
        BeginningTraditionFactory(beginning=cls.beginning, tradition=cls.tradition)
        cls.path = PathFactory()
        cls.gift = GiftFactory()
        cls.strike = TechniqueFactory(gift=cls.gift, name="Strike", damage_profile=False)
        cls.ward = TechniqueFactory(gift=cls.gift, name="Ward", damage_profile=False)
        cls.hex = TechniqueFactory(gift=cls.gift, name="Hex", damage_profile=False)
        grant = PathGiftGrantFactory(path=cls.path, gift=cls.gift)
        grant.starter_techniques.add(cls.strike, cls.ward)
        special = TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift)
        special.special_techniques.add(cls.hex)
        cls.species = SpeciesFactory()
        species_grant = SpeciesGiftGrantFactory(species=cls.species)
        cls.species_technique = TechniqueFactory(
            gift=species_grant.gift, name="Claws", damage_profile=False
        )

    def setUp(self) -> None:
        cache.clear()
        self.addCleanup(cache.clear)

    def _canned(self) -> dict[int, TechniquePowerReport]:
        return {
            self.strike.pk: _report(
                self.strike.pk,
                "Strike",
                baseline_de=9.0,
                formula_baseline_de=9.0,
                valuations=(_valuation("damage", 9.0, ValuationProvenance.FORMULA),),
                flags=(FLAG_NOT_CASTABLE_STANDALONE,),
            ),
            self.ward.pk: _report(
                self.ward.pk,
                "Ward",
                baseline_de=4.0,
                formula_baseline_de=4.0,
                valuations=(_valuation("mitigation", 4.0, ValuationProvenance.PARSED),),
            ),
            self.hex.pk: _report(
                self.hex.pk,
                "Hex",
                baseline_de=6.0,
                estimated_baseline_de=6.0,
                valuations=(_valuation("control", 6.0, ValuationProvenance.ESTIMATE),),
            ),
            self.species_technique.pk: _report(
                self.species_technique.pk,
                "Claws",
                baseline_de=12.0,
                formula_baseline_de=12.0,
                valuations=(_valuation("damage", 12.0, ValuationProvenance.FORMULA),),
            ),
        }

    def _build(self, **params: Any) -> ta.StartingKitReport:
        canned = self._canned()
        kit_params = ta.StartingKitParams(
            beginning=self.beginning,
            tradition=self.tradition,
            path=self.path,
            gift=self.gift,
            **params,
        )
        with (
            patch(_EVALUATE, side_effect=lambda t, *_a, **_k: canned[t.pk]) as evaluate,
            patch(_REFERENCE, return_value=_FRAME),
            patch(_BANDS, return_value=[]),
        ):
            report = ta.build_starting_kit_report(kit_params)
        self.evaluate_calls = evaluate.call_args_list
        return report

    def test_prices_path_and_tradition_options_at_the_starting_context(self) -> None:
        report = self._build()
        self.assertEqual(
            {(row.report.name, row.source) for row in report.rows},
            {
                ("Strike", ta.OptionSource.PATH),
                ("Ward", ta.OptionSource.PATH),
                ("Hex", ta.OptionSource.TRADITION),
            },
        )
        context = self.evaluate_calls[0].args[1]
        self.assertEqual((context.level, context.thread_level), (1, 0))

    def test_species_options_join_only_when_a_species_is_given(self) -> None:
        self.assertNotIn("Claws", [row.report.name for row in self._build().rows])
        with_species = self._build(species=self.species)
        claws = next(row for row in with_species.rows if row.report.name == "Claws")
        self.assertEqual(claws.source, ta.OptionSource.SPECIES)

    def test_rows_rank_by_baseline_de_and_the_kit_is_the_pick_budget(self) -> None:
        report = self._build()
        self.assertEqual([row.report.name for row in report.rows], ["Strike", "Hex", "Ward"])
        self.assertEqual(report.pick_budget, 1)
        self.assertEqual([row.in_kit for row in report.rows], [True, False, False])
        self.assertAlmostEqual(report.kit_baseline_de, 9.0)

    def test_extra_picks_widen_the_kit(self) -> None:
        report = self._build(extra_picks=1)
        self.assertEqual(report.pick_budget, 2)
        self.assertAlmostEqual(report.kit_baseline_de, 15.0)
        self.assertAlmostEqual(report.kit_formula_de, 9.0)
        self.assertAlmostEqual(report.kit_estimate_de, 6.0)

    def test_uncastable_options_are_priced_and_flagged(self) -> None:
        report = self._build()
        strike = next(row for row in report.rows if row.report.name == "Strike")
        self.assertFalse(strike.castable)
        self.assertEqual(report.castable_count, 2)

    def test_floor_needs_a_damage_option_and_a_protection_option(self) -> None:
        self.assertTrue(self._build().floor.met)

    def test_mostly_estimate_marks_an_estimate_built_option(self) -> None:
        report = self._build()
        hex_row = next(row for row in report.rows if row.report.name == "Hex")
        self.assertTrue(hex_row.mostly_estimate)
        strike = next(row for row in report.rows if row.report.name == "Strike")
        self.assertFalse(strike.mostly_estimate)

    def test_anchor_de_is_read_only_from_a_cached_catalog_corpus(self) -> None:
        self.assertIsNone(self._build().rows[0].anchor_de)
        anchor_params = ta.TechniqueAnalyticsParams()
        cache.set(
            ta._corpus_cache_key(anchor_params),
            ([_report(self.strike.pk, "Strike", baseline_de=40.0)], _FRAME),
        )
        canned = self._canned()
        kit_params = ta.StartingKitParams(
            beginning=self.beginning, tradition=self.tradition, path=self.path, gift=self.gift
        )
        with (
            patch(_EVALUATE, side_effect=lambda t, *_a, **_k: canned[t.pk]),
            patch(_REFERENCE, return_value=_FRAME),
            patch(_BANDS, return_value=[]),
        ):
            report = ta.build_starting_kit_report(kit_params, anchor_params=anchor_params)
        strike = next(row for row in report.rows if row.report.name == "Strike")
        self.assertAlmostEqual(strike.anchor_de, 40.0)


_EVALUATE_ALL = (
    "web.admin.tuning.technique_analytics.technique_power_eval.evaluate_all_with_reference"
)


class PoolScanTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.voice = PathFactory(name="Path of the Voice")
        cls.steel = PathFactory(name="Path of Steel")
        cls.gift = GiftFactory(name="Oathcraft")
        cls.strike = TechniqueFactory(gift=cls.gift, name="Strike", damage_profile=False)
        cls.ward = TechniqueFactory(gift=cls.gift, name="Ward", damage_profile=False)
        cls.hex = TechniqueFactory(gift=cls.gift, name="Hex", damage_profile=False)
        steel_grant = PathGiftGrantFactory(path=cls.steel, gift=cls.gift)
        steel_grant.starter_techniques.add(cls.strike, cls.ward)
        voice_grant = PathGiftGrantFactory(path=cls.voice, gift=cls.gift)
        voice_grant.starter_techniques.add(cls.hex, cls.ward)
        PathGiftGrantFactory(path=PathFactory(name="Path of Tomes"), gift=cls.gift)

    def setUp(self) -> None:
        cache.clear()
        self.addCleanup(cache.clear)

    def _corpus(self) -> tuple[list[TechniquePowerReport], ReferenceFrame]:
        return (
            [
                _report(
                    self.strike.pk,
                    "Strike",
                    baseline_de=9.0,
                    valuations=(_valuation("damage", 9.0, ValuationProvenance.FORMULA),),
                    flags=(FLAG_NOT_CASTABLE_STANDALONE,),
                ),
                _report(
                    self.ward.pk,
                    "Ward",
                    baseline_de=4.0,
                    valuations=(_valuation("mitigation", 4.0, ValuationProvenance.PARSED),),
                    flags=(FLAG_NOT_CASTABLE_STANDALONE,),
                ),
                _report(
                    self.hex.pk,
                    "Hex",
                    baseline_de=6.0,
                    valuations=(_valuation("debuff", 6.0, ValuationProvenance.FORMULA),),
                ),
            ],
            _FRAME,
        )

    def test_one_row_per_pool_with_techniques(self) -> None:
        with patch(_EVALUATE_ALL, return_value=self._corpus()):
            rows = ta.build_pool_scan()
        self.assertEqual([row.path_name for row in rows], ["Path of Steel", "Path of the Voice"])
        steel = rows[0]
        self.assertEqual((steel.option_count, steel.castable_count), (2, 0))
        self.assertTrue(steel.floor.met)
        self.assertAlmostEqual(steel.best_single_de, 9.0)
        voice = rows[1]
        self.assertFalse(voice.floor.has_damage)
        self.assertTrue(voice.floor.has_protection)
        self.assertEqual(voice.castable_count, 1)

    def test_evaluates_the_catalog_once_at_the_starting_context_and_caches_it(self) -> None:
        with patch(_EVALUATE_ALL, return_value=self._corpus()) as evaluate_all:
            ta.build_pool_scan()
            ta.build_pool_scan()
        evaluate_all.assert_called_once()
        context = evaluate_all.call_args.args[0]
        self.assertEqual((context.level, context.thread_level), (1, 0))

    def test_filters_and_counts(self) -> None:
        with patch(_EVALUATE_ALL, return_value=self._corpus()):
            rows = ta.build_pool_scan()
        failing = ta.filter_pool_scan(rows, ta.PoolScanFilter.FAILS_FLOOR)
        self.assertEqual([row.path_name for row in failing], ["Path of the Voice"])
        nothing = ta.filter_pool_scan(rows, ta.PoolScanFilter.NOTHING_CASTABLE)
        self.assertEqual([row.path_name for row in nothing], ["Path of Steel"])
        self.assertEqual(
            ta.count_pool_scan(rows), ta.PoolScanCounts(fails_floor=1, nothing_castable=1, all=2)
        )

    def test_unknown_filter_value_falls_back_to_the_default(self) -> None:
        self.assertEqual(ta.resolve_pool_scan_filter("bogus"), ta.PoolScanFilter.FAILS_FLOOR)
        self.assertEqual(ta.resolve_pool_scan_filter("all"), ta.PoolScanFilter.ALL)

    def test_clear_corpus_cache_drops_the_catalog_entry(self) -> None:
        params = ta.TechniqueAnalyticsParams()
        cache.set(ta._corpus_cache_key(params), self._corpus())
        ta.clear_corpus_cache(params)
        self.assertIsNone(cache.get(ta._corpus_cache_key(params)))


class CombatFloorTests(TestCase):
    def test_debuff_and_control_count_for_neither(self) -> None:
        debuff = _valuation("debuff", 5.0, ValuationProvenance.FORMULA)
        control = _valuation("control", 5.0, ValuationProvenance.ESTIMATE)
        floor = ta.meets_combat_floor(
            [
                _report(1, "Hex", valuations=(debuff,)),
                _report(2, "Hold", valuations=(control,)),
            ]
        )
        self.assertFalse(floor.has_damage)
        self.assertFalse(floor.has_protection)
        self.assertFalse(floor.met)

    def test_heal_counts_as_protection_and_zero_values_do_not_count(self) -> None:
        heal = _valuation("heal", 3.0, ValuationProvenance.FORMULA)
        zero_damage = _valuation("damage", 0.0, ValuationProvenance.FORMULA)
        floor = ta.meets_combat_floor(
            [
                _report(1, "Mend", valuations=(heal,)),
                _report(2, "Dud", valuations=(zero_damage,)),
            ]
        )
        self.assertTrue(floor.has_protection)
        self.assertFalse(floor.has_damage)
