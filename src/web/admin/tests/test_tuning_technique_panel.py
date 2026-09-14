"""Tests for the Techniques combat-power panel view (#3279 Task 3).

Evaluating the whole technique catalog is real DB work (see
`technique_analytics.py`'s module docstring), so every test here patches
`web.admin.tuning.technique_analytics.build_technique_panel` at its origin with a
canned, distinctive `TechniquePanelData` and asserts the mock was actually invoked
(or not) rather than exercising the real evaluator - mirrors
`test_tuning_simulation_view.py`'s patching discipline.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from django.core.cache import cache
from django.template.defaultfilters import date as date_filter
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from evennia.accounts.models import AccountDB

from web.admin.tuning.technique_analytics import (
    TechniqueAnalyticsParams,
    TechniquePanelData,
    TechniqueRow,
)
from world.magic.types.technique_power import (
    PayloadValuation,
    ReferenceFrame,
    TechniquePowerReport,
    ValuationProvenance,
)

_PATCH_TARGET = "web.admin.tuning.technique_analytics.build_technique_panel"


def _canned_report(**overrides: Any) -> TechniquePowerReport:
    defaults: dict[str, Any] = {
        "technique_id": 1,
        "name": "Distinctive Firebolt",
        "gift_name": "Pyromancy",
        "level": 4,
        "tier": 1,
        "category": "Attack",
        "baseline_power": 4,
        "amplified_power": 6,
        "baseline_de": 11.0,
        "amplified_de": 16.5,
        "valuations": (
            PayloadValuation(
                kind="damage",
                label="fire",
                value=11.0,
                provenance=ValuationProvenance.FORMULA,
                detail="E[budget x mult] over SL bands = 11.00",
            ),
        ),
        "effective_anima": 5,
        "de_per_anima": 2.2,
        "flags": (),
    }
    defaults.update(overrides)
    return TechniquePowerReport(**defaults)


def _canned_panel(**overrides: Any) -> TechniquePanelData:
    params = overrides.pop("params", None) or TechniqueAnalyticsParams()
    report = overrides.pop("report", None) or _canned_report()
    rows = overrides.pop("rows", [TechniqueRow(report=report, amplification_ratio=1.5)])
    defaults: dict[str, Any] = {
        "rows": rows,
        "zero_bucket": [],
        "provenance_summary": {"FORMULA": 1},
        "params": params,
        "reference": ReferenceFrame(
            outgoing_dpr=9.5, incoming_dpr=9.5, source_label="median-attack estimate"
        ),
        "evaluated_at": timezone.now(),
    }
    defaults.update(overrides)
    return TechniquePanelData(**defaults)


class TestTechniqueFragmentView(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser(
            "roottechadmin", "roottech@example.com", "pw-123456"
        )
        cls.staff = AccountDB.objects.create_user("techstaffer", "ts@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

    def setUp(self) -> None:
        cache.clear()
        self.addCleanup(cache.clear)

    def _post_data(self, **overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "level": 10,
            "thread_level": 3,
            "roller_points": 25,
            "target_difficulty": 25,
            "roll_modifier": 0,
            "sort": "baseline_de",
        }
        data.update(overrides)
        return data

    def test_anonymous_get_redirected_to_login(self) -> None:
        resp = self.client.get(reverse("admin_tuning_techniques"))
        self.assertEqual(resp.status_code, 302)

    def test_staff_non_superuser_get_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_tuning_techniques"))
        self.assertEqual(resp.status_code, 403)

    def test_get_with_no_cache_renders_empty_state(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_tuning_techniques"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('id="panel-techniques-form"', body)
        self.assertIn('id="panel-techniques-refresh"', body)
        self.assertIn("Starting kits", body)
        self.assertIn("No evaluation has been run yet", body)
        self.assertIn("Tradition (this Beginning", body)
        self.assertIn("Species (optional)", body)
        self.assertIn("Extra picks from distinctions", body)
        self.assertIn('hx-trigger="load"', body)
        self.assertIn(f'hx-get="{reverse("admin_tuning_techniques")}?scan=fails_floor"', body)

    @patch(_PATCH_TARGET)
    def test_evaluated_at_renders_next_to_the_refresh_note(self, mock_build: Any) -> None:
        when = timezone.now()
        mock_build.return_value = _canned_panel(evaluated_at=when)
        self.client.force_login(self.super)
        resp = self.client.post(reverse("admin_tuning_techniques"), self._post_data())
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn(f"Evaluated {date_filter(when, 'Y-m-d H:i')}.", body)

    @patch(_PATCH_TARGET)
    def test_post_valid_superuser_builds_panel_and_renders_rows(self, mock_build: Any) -> None:
        mock_build.return_value = _canned_panel()
        self.client.force_login(self.super)
        resp = self.client.post(reverse("admin_tuning_techniques"), self._post_data())

        self.assertEqual(resp.status_code, 200)
        mock_build.assert_called_once()

        called_params = mock_build.call_args.args[0]
        self.assertIsInstance(called_params, TechniqueAnalyticsParams)
        self.assertEqual(called_params.level, 10)
        self.assertEqual(called_params.thread_level, 3)
        self.assertEqual(called_params.roller_points, 25)
        self.assertEqual(called_params.target_difficulty, 25)
        self.assertEqual(called_params.roll_modifier, 0)
        self.assertEqual(called_params.sort, "baseline_de")

        body = resp.content.decode()
        self.assertIn("Distinctive Firebolt", body)
        self.assertIn("Pyromancy", body)

    @patch(_PATCH_TARGET)
    def test_get_after_post_returns_cached_result_without_rebuilding(self, mock_build: Any) -> None:
        mock_build.return_value = _canned_panel()
        self.client.force_login(self.super)

        post_resp = self.client.post(reverse("admin_tuning_techniques"), self._post_data())
        self.assertEqual(post_resp.status_code, 200)

        get_resp = self.client.get(reverse("admin_tuning_techniques"))
        self.assertEqual(get_resp.status_code, 200)

        mock_build.assert_called_once()
        body = get_resp.content.decode()
        self.assertIn("Distinctive Firebolt", body)

    @patch(_PATCH_TARGET)
    def test_get_with_unknown_sort_falls_back_to_baseline_de(self, mock_build: Any) -> None:
        mock_build.return_value = _canned_panel(params=TechniqueAnalyticsParams(sort="baseline_de"))
        self.client.force_login(self.super)

        self.client.post(reverse("admin_tuning_techniques"), self._post_data())
        resp = self.client.get(reverse("admin_tuning_techniques"), {"sort": "not-a-real-key"})

        self.assertEqual(resp.status_code, 200)
        # An unrecognized sort resolves to the same "baseline_de" the cached
        # panel was already built with, so no second build is triggered.
        mock_build.assert_called_once()
        body = resp.content.decode()
        self.assertIn("Distinctive Firebolt", body)

    @patch(_PATCH_TARGET)
    def test_get_with_different_known_sort_rebuilds_panel(self, mock_build: Any) -> None:
        mock_build.side_effect = [
            _canned_panel(params=TechniqueAnalyticsParams(sort="baseline_de")),
            _canned_panel(params=TechniqueAnalyticsParams(sort="name")),
        ]
        self.client.force_login(self.super)

        self.client.post(reverse("admin_tuning_techniques"), self._post_data())
        resp = self.client.get(reverse("admin_tuning_techniques"), {"sort": "name"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(mock_build.call_count, 2)
        second_call_params = mock_build.call_args.args[0]
        self.assertEqual(second_call_params.sort, "name")

    @patch(_PATCH_TARGET)
    def test_post_out_of_range_level_is_clamped_not_rejected(self, mock_build: Any) -> None:
        mock_build.return_value = _canned_panel()
        self.client.force_login(self.super)
        resp = self.client.post(
            reverse("admin_tuning_techniques"),
            self._post_data(level=999, thread_level=-5),
        )

        self.assertEqual(resp.status_code, 200)
        mock_build.assert_called_once()
        called_params = mock_build.call_args.args[0]
        self.assertEqual(called_params.level, 30)
        self.assertEqual(called_params.thread_level, 0)

    @patch(_PATCH_TARGET)
    def test_post_invalid_sort_choice_rerenders_form_errors_without_building(
        self, mock_build: Any
    ) -> None:
        self.client.force_login(self.super)
        resp = self.client.post(
            reverse("admin_tuning_techniques"), self._post_data(sort="not-a-real-key")
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("errorlist", body)
        mock_build.assert_not_called()

    @patch(_PATCH_TARGET)
    def test_zero_bucket_and_provenance_summary_render(self, mock_build: Any) -> None:
        inert_report = _canned_report(
            technique_id=2,
            name="Inert Placeholder",
            baseline_de=0.0,
            amplified_de=0.0,
            valuations=(
                PayloadValuation(
                    kind="capability",
                    label="Latent Spark",
                    value=0.0,
                    provenance=ValuationProvenance.INERT_PAYLOAD,
                    detail="no capability-grant cast seam exists",
                ),
            ),
            de_per_anima=0.0,
        )
        mock_build.return_value = _canned_panel(
            zero_bucket=[inert_report],
            provenance_summary={"FORMULA": 1, "INERT_PAYLOAD": 1},
        )
        self.client.force_login(self.super)
        resp = self.client.post(reverse("admin_tuning_techniques"), self._post_data())

        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Inert Placeholder", body)
        self.assertIn("INERT_PAYLOAD", body)


class TestTechniquePanelCatalogRevision(TestCase):
    """An authoring edit must invalidate both cache layers (#3682).

    Both the corpus cache (24h, keyed on the numeric knobs) and the rendered
    panel cache were keyed on parameters alone, so re-submitting the same
    parameters after editing a technique served the pre-edit corpus: staff tuned
    against the numbers they had just changed and saw no movement.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser(
            "revtechadmin", "revtech@example.com", "pw-123456"
        )

    def setUp(self) -> None:
        cache.clear()
        self.addCleanup(cache.clear)

    def _post_data(self) -> dict[str, Any]:
        return {
            "level": 10,
            "thread_level": 3,
            "roller_points": 25,
            "target_difficulty": 25,
            "roll_modifier": 0,
            "sort": "baseline_de",
        }

    @patch(_PATCH_TARGET)
    def test_authoring_edit_forces_a_rebuild_on_identical_params(self, mock_build: Any) -> None:
        from world.magic.factories import BinaryEffectTypeFactory, TechniqueFactory
        from world.magic.services.technique_effects import invalidate_technique_payload_caches

        mock_build.return_value = _canned_panel()
        self.client.force_login(self.super)
        self.client.post(reverse("admin_tuning_techniques"), self._post_data())
        self.assertEqual(mock_build.call_count, 1)

        # The one seam every authoring write already passes through.
        technique = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        invalidate_technique_payload_caches(technique)

        self.client.post(reverse("admin_tuning_techniques"), self._post_data())
        self.assertEqual(mock_build.call_count, 2)

    @patch(_PATCH_TARGET)
    def test_get_after_an_edit_does_not_re_render_the_stale_panel(self, mock_build: Any) -> None:
        """The last-key pointer is revision-scoped, so GET shows nothing stale."""
        from world.magic.factories import BinaryEffectTypeFactory, TechniqueFactory
        from world.magic.services.technique_effects import invalidate_technique_payload_caches

        mock_build.return_value = _canned_panel()
        self.client.force_login(self.super)
        self.client.post(reverse("admin_tuning_techniques"), self._post_data())

        technique = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        invalidate_technique_payload_caches(technique)

        resp = self.client.get(reverse("admin_tuning_techniques"))

        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("Distinctive Firebolt", resp.content.decode())


class TestTechniqueCatalogRevision(TestCase):
    """The revision counter itself (#3682)."""

    def setUp(self) -> None:
        cache.clear()
        self.addCleanup(cache.clear)

    def test_revision_starts_at_zero_and_rises_on_each_bump(self) -> None:
        from world.magic.services.technique_effects import (
            bump_technique_catalog_revision,
            technique_catalog_revision,
        )

        self.assertEqual(technique_catalog_revision(), 0)
        bump_technique_catalog_revision()
        self.assertEqual(technique_catalog_revision(), 1)
        bump_technique_catalog_revision()
        self.assertEqual(technique_catalog_revision(), 2)

    def test_corpus_cache_key_changes_with_the_revision(self) -> None:
        from web.admin.tuning.technique_analytics import _corpus_cache_key
        from world.magic.services.technique_effects import bump_technique_catalog_revision

        params = TechniqueAnalyticsParams()
        before = _corpus_cache_key(params)
        bump_technique_catalog_revision()

        self.assertNotEqual(before, _corpus_cache_key(params))


_KIT_TARGET = "web.admin.tuning.technique_analytics.build_starting_kit_report"
_SCAN_TARGET = "web.admin.tuning.technique_analytics.build_pool_scan"
_CLEAR_TARGET = "web.admin.tuning.technique_analytics.clear_corpus_cache"


class TestTechniquePanelStartingKits(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_creation.factories import (
            BeginningsFactory,
            BeginningTraditionFactory,
        )
        from world.classes.factories import PathFactory
        from world.magic.factories import GiftFactory, TraditionFactory

        cls.super = AccountDB.objects.create_superuser("kitadmin", "kit@example.com", "pw-123456")
        cls.beginning = BeginningsFactory()
        cls.tradition = TraditionFactory()
        cls.other_tradition = TraditionFactory()
        BeginningTraditionFactory(beginning=cls.beginning, tradition=cls.tradition)
        cls.path = PathFactory()
        cls.gift = GiftFactory()

    def setUp(self) -> None:
        cache.clear()
        self.addCleanup(cache.clear)
        self.client.force_login(self.super)

    def _kit_data(self, **overrides: Any) -> dict[str, Any]:
        from world.character_creation.constants import REQUIRED_STATS

        data: dict[str, Any] = {
            "intent": "kit",
            "beginning": self.beginning.pk,
            "tradition": self.tradition.pk,
            "path": self.path.pk,
            "gift": self.gift.pk,
            "species": "",
            "extra_picks": 1,
        }
        data.update(dict.fromkeys(REQUIRED_STATS, 2))
        data.update(overrides)
        return data

    def _empty_kit(self) -> Any:
        from web.admin.tuning import technique_analytics as ta

        params = ta.StartingKitParams(
            beginning=self.beginning, tradition=self.tradition, path=self.path, gift=self.gift
        )
        return ta.StartingKitReport(
            params=params,
            roller_points=25,
            pick_budget=2,
            rows=(),
            kit_baseline_de=0.0,
            kit_formula_de=0.0,
            kit_estimate_de=0.0,
            castable_count=0,
            floor=ta.FloorResult(has_damage=False, has_protection=False),
        )

    @patch(_KIT_TARGET)
    def test_kit_post_builds_the_report_from_the_form(self, mock_kit: Any) -> None:
        mock_kit.return_value = self._empty_kit()
        resp = self.client.post(reverse("admin_tuning_techniques"), self._kit_data())
        self.assertEqual(resp.status_code, 200)
        mock_kit.assert_called_once()
        params = mock_kit.call_args.args[0]
        self.assertEqual((params.path, params.gift, params.extra_picks), (self.path, self.gift, 1))
        self.assertIsNone(params.species)
        body = resp.content.decode()
        self.assertIn('id="panel-techniques-kit"', body)
        self.assertNotIn("Options ()", body)

    @patch(_KIT_TARGET)
    def test_kit_result_renders_option_rows_and_tiles(self, mock_kit: Any) -> None:
        from web.admin.tuning import technique_analytics as ta

        report = _canned_report(
            technique_id=99,
            name="Champions Charge",
            baseline_de=11.2,
            formula_baseline_de=9.8,
            estimated_baseline_de=1.4,
            flags=(ta.FLAG_NOT_CASTABLE_STANDALONE, "underspecified"),
        )
        params = ta.StartingKitParams(
            beginning=self.beginning,
            tradition=self.tradition,
            path=self.path,
            gift=self.gift,
            extra_picks=1,
        )
        row = ta.KitOptionRow(
            report=report,
            source=ta.OptionSource.PATH,
            castable=False,
            mostly_estimate=False,
            anchor_de=38.5,
            in_kit=True,
        )
        mock_kit.return_value = ta.StartingKitReport(
            params=params,
            roller_points=25,
            pick_budget=2,
            rows=(row,),
            kit_baseline_de=11.2,
            kit_formula_de=9.8,
            kit_estimate_de=1.4,
            castable_count=0,
            floor=ta.FloorResult(has_damage=True, has_protection=True),
        )
        resp = self.client.post(reverse("admin_tuning_techniques"), self._kit_data())
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Champions Charge", body)
        self.assertIn("kit-row-in-kit", body)
        self.assertIn('class="stat-value pass">Met', body)
        self.assertIn("Picks (1 base, 1 from distinctions)", body)
        self.assertIn("Options (1 path)", body)
        self.assertIn("not castable", body)
        self.assertIn("underspecified", body)
        self.assertNotIn("not_castable_standalone", body)
        self.assertIn("38.5", body)
        self.assertIn("damage", body)

    @patch(_KIT_TARGET)
    def test_tradition_not_offered_by_the_beginning_is_a_form_error(self, mock_kit: Any) -> None:
        resp = self.client.post(
            reverse("admin_tuning_techniques"),
            self._kit_data(tradition=self.other_tradition.pk),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("errorlist", resp.content.decode())
        mock_kit.assert_not_called()

    @patch(_PATCH_TARGET)
    @patch(_CLEAR_TARGET)
    def test_refresh_clears_the_corpus_and_rebuilds(self, mock_clear: Any, mock_build: Any) -> None:
        mock_build.return_value = _canned_panel()
        data = {
            "intent": "refresh",
            "level": 10,
            "thread_level": 3,
            "roller_points": 25,
            "target_difficulty": 25,
            "roll_modifier": 0,
            "sort": "baseline_de",
        }
        resp = self.client.post(reverse("admin_tuning_techniques"), data)
        self.assertEqual(resp.status_code, 200)
        mock_clear.assert_called_once()
        mock_build.assert_called_once()

    @patch(_SCAN_TARGET)
    def test_scan_get_renders_the_filtered_pool_scan(self, mock_scan: Any) -> None:
        from web.admin.tuning import technique_analytics as ta

        mock_scan.return_value = (
            ta.PoolScanRow(
                path_id=self.path.pk,
                path_name="Distinctive Path",
                gift_id=self.gift.pk,
                gift_name="Distinctive Gift",
                option_count=4,
                castable_count=0,
                floor=ta.FloorResult(has_damage=False, has_protection=True),
                best_single_de=3.1,
            ),
        )
        resp = self.client.get(reverse("admin_tuning_techniques"), {"scan": "fails_floor"})
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('id="panel-techniques-pool-scan"', body)
        self.assertIn("Distinctive Path", body)
        self.assertIn(f"kit_path={self.path.pk}", body)
        self.assertIn("One row per path and gift pairing", body)
        self.assertIn("All pools", body)
        self.assertNotIn("All pools (", body)

    def test_price_kit_link_prefills_path_and_gift(self) -> None:
        resp = self.client.get(
            reverse("admin_tuning_techniques"),
            {"kit_path": self.path.pk, "kit_gift": self.gift.pk},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn(f'value="{self.path.pk}" selected', body)
