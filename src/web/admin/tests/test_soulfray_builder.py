"""The Soulfray Stage Builder page: read side, reachability, styling (#4089)."""

from __future__ import annotations

from pathlib import Path
import re

from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from actions.factories import ConsequencePoolEntryFactory
from evennia_extensions.models import PlayerData
from web.admin.soulfray_builder.forms import (
    SPIN_THE_WHEEL_HELP,
    build_forms,
    consequence_table,
)
from web.admin.tests.soulfray_ladder import (
    SoulfrayBuilderTestCase,
    _superuser,
    build_ladder,
    form_values,
    shared_pool,
    stock,
)
from web.admin.tests.test_distinction_builder import (
    emitted_classes,
    reachable_css,
    stylesheet_hrefs,
)
from world.checks.constants import EffectType
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory
from world.checks.models import Consequence
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.contributors.factories import ContentContributorFactory
from world.magic.factories import SoulfrayConfigFactory
from world.magic.services.soulfray import soulfray_ladder_summary


class SoulfrayPageTestCase(SoulfrayBuilderTestCase):
    """The shared ladder plus this module's credit, config, pools and a foreign stage."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.writer = ContentContributorFactory(name="Soulfray Writer")
        PlayerData.objects.create(account=cls.author, contributor=cls.writer)
        cls.unlinked = _superuser("sfunlinked")
        cls.config = SoulfrayConfigFactory(
            resilience_check_type=CheckTypeFactory(name="Magical Endurance")
        )
        cls.common = shared_pool(cls.ladder, ("Partial Success", "Success"))
        cls.fraying = cls.ladder.stage("Fraying")
        cls.tearing = cls.ladder.stage("Tearing")
        cls.fraying_pool = stock(
            cls.fraying, cls.ladder, tiers=("Critical Failure", "Failure"), parent=cls.common
        )
        cls.fraying_failure = Consequence.objects.get(label="Fraying Failure")
        cls.shaken = ConditionTemplateFactory(name="Shaken")
        ConsequenceEffectFactory(
            consequence=cls.fraying_failure,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=cls.shaken,
            condition_severity=1,
        )
        cls.numb = ConditionStageFactory(
            condition=ConditionTemplateFactory(name="Poison test", has_progression=True),
            stage_order=1,
            name="Numb",
        )

    def _get(self, stage, query: str = "", user=None):
        self.client.force_login(user or self.author)
        return self.client.get(reverse("admin_soulfray_builder", args=[stage.pk]) + query)


class BuilderGetTest(SoulfrayPageTestCase):
    def test_renders_every_module_and_the_rail(self) -> None:
        resp = self._get(self.tearing)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        for heading in (
            "The ladder",
            "The stage",
            "The resilience roll at this stage",
            "What the roll can draw",
            "This stage",
            "Danger",
            "Checks",
            "Credit",
        ):
            self.assertIn(heading, body)
        for stage in self.ladder.stages:
            self.assertIn(stage.name, body)
        self.assertIn("Magical Endurance", body)
        self.assertIn("Save and open Ripping", body)
        self.assertIn("no Soulfray stage can kill. Soulfray is meant to be able to.", body)

    def test_spin_the_wheel_column_carries_its_help_text(self) -> None:
        body = self._get(self.fraying).content.decode()
        self.assertIn(f'title="{SPIN_THE_WHEEL_HELP}"', body)
        self.assertIn(">Spin the wheel</abbr>", body)
        self.assertIn("Spin the wheel: when the roll lands on that result", body)

    def test_shared_rows_name_their_pool_and_own_rows_say_this_stage(self) -> None:
        body = self._get(self.fraying).content.decode()
        self.assertIn('value="common Success"', body)
        self.assertIn("Soulfray - common", body)
        self.assertIn("this stage", body)
        self.assertIn("Apply Condition, self, Shaken sev 1", body)

    def test_a_stage_from_another_condition_is_404(self) -> None:
        self.assertEqual(self._get(self.numb).status_code, 404)

    def test_unlinked_operator_sees_setup_guidance(self) -> None:
        body = self._get(self.tearing, user=self.unlinked).content.decode()
        self.assertIn("link a contributor", body.lower())

    def test_copy_from_prefills_the_stage_below(self) -> None:
        body = self._get(self.tearing, f"?copy_from={self.fraying.pk}").content.decode()
        self.assertIn('value="Fraying Failure"', body)
        self.assertRegex(body, rf'name="rows-\d+-copy_of"[^>]*value="{self.fraying_failure.pk}"')
        self.assertIn(f"Copy rows from {self.fraying.name}", body)
        self.assertIn(f"copies 1 effect from {self.fraying.name}", body)

    def test_a_staff_non_superuser_is_refused(self) -> None:
        staff = AccountDB.objects.create_user("sfstaff", "sfstaff@example.com", "pw-123456")
        staff.is_staff = True
        staff.save()
        self.assertEqual(self._get(self.tearing, user=staff).status_code, 403)


class ConsequenceTableTest(SoulfrayPageTestCase):
    """P11: the table's own walk agrees with the draw's merge rule."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        common_success = Consequence.objects.get(label="common Success")
        common_partial = Consequence.objects.get(label="common Partial Success")
        # Fraying reweights one shared row and drops the other.
        ConsequencePoolEntryFactory(
            pool=cls.fraying_pool, consequence=common_success, weight_override=7
        )
        ConsequencePoolEntryFactory(
            pool=cls.fraying_pool, consequence=common_partial, is_excluded=True
        )
        cls.common_success = common_success
        cls.common_partial = common_partial

    def test_effective_rows_and_weights_match_the_ladder_summary(self) -> None:
        table = consequence_table(self.fraying_pool)
        summary = next(s for s in soulfray_ladder_summary() if s.stage.pk == self.fraying.pk)
        self.assertEqual(
            sorted((row.consequence.pk, row.weight) for row in table if not row.dropped),
            sorted((wc.consequence.pk, wc.weight) for wc in summary.consequences),
        )

    def test_dropped_shared_rows_still_show_so_they_can_be_restored(self) -> None:
        rows = {row.consequence.pk: row for row in consequence_table(self.fraying_pool)}
        self.assertTrue(rows[self.common_partial.pk].dropped)
        self.assertEqual(rows[self.common_success.pk].weight, 7)
        self.assertEqual(rows[self.common_success.pk].shared_from, self.common)


class NewRowEffectsFormTest(SoulfrayPageTestCase):
    """P3: a row added on the page carries its own effects formset, keyed by row index."""

    def test_the_add_row_template_carries_a_placeholder_effects_formset(self) -> None:
        body = self._get(self.fraying).content.decode()
        template = re.search(
            r'<template id="empty-row-template">(.*?)</template>', body, flags=re.DOTALL
        ).group(1)
        self.assertIn('name="new__prefix__-TOTAL_FORMS"', template)
        self.assertIn('data-new-row="1"', template)
        shared = re.search(
            r'<template id="empty-effect-new">(.*?)</template>', body, flags=re.DOTALL
        ).group(1)
        self.assertIn('name="new__prefix__-__prefix__-effect_type"', shared)

    def test_copied_rows_render_their_own_new_row_effects_formset(self) -> None:
        body = self._get(self.tearing, f"?copy_from={self.fraying.pk}").content.decode()
        values = form_values(body)
        self.assertEqual(values["rows-TOTAL_FORMS"], ["2"])
        self.assertEqual(values["new0-TOTAL_FORMS"], ["0"])
        self.assertEqual(values["new1-TOTAL_FORMS"], ["0"])

    def _posted(self, extra: dict[str, list[str]]) -> QueryDict:
        values = form_values(self._get(self.fraying).content.decode())
        values.update(extra)
        data = QueryDict(mutable=True)
        for key, items in values.items():
            data.setlist(key, items)
        return data

    def test_a_posted_new_row_binds_its_effects_against_an_unsaved_consequence(self) -> None:
        index = len(consequence_table(self.fraying_pool))
        data = self._posted(
            {
                "rows-TOTAL_FORMS": [str(index + 1)],
                f"rows-{index}-outcome_tier": [str(self.ladder.outcomes["Failure"].pk)],
                f"rows-{index}-label": ["PLACEHOLDER new row"],
                f"rows-{index}-weight": ["2"],
                f"new{index}-TOTAL_FORMS": ["1"],
                f"new{index}-INITIAL_FORMS": ["0"],
                f"new{index}-0-effect_type": [EffectType.APPLY_CONDITION],
                f"new{index}-0-target": ["self"],
                f"new{index}-0-execution_order": ["0"],
                f"new{index}-0-condition_template": [str(self.shaken.pk)],
                f"new{index}-0-condition_severity": ["2"],
            }
        )
        forms = build_forms(data, self.fraying, self.config, None)
        effects = forms.new_effects[index]
        self.assertIsNone(effects.instance.pk)
        self.assertTrue(effects.is_valid(), effects.errors)
        self.assertEqual(len(effects.forms), 1)
        self.assertTrue(effects.forms[0].has_changed())

    def test_a_new_row_posted_without_an_effects_management_form_has_no_effects(self) -> None:
        index = len(consequence_table(self.fraying_pool))
        data = self._posted({"rows-TOTAL_FORMS": [str(index + 1)]})
        effects = build_forms(data, self.fraying, self.config, None).new_effects[index]
        self.assertTrue(effects.is_valid(), effects.errors)
        self.assertEqual(effects.forms, [])


class IndexAndPickTest(SoulfrayPageTestCase):
    def test_index_opens_the_first_stage(self) -> None:
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_soulfray_builder_index"))
        self.assertRedirects(
            resp,
            reverse("admin_soulfray_builder", args=[self.fraying.pk]),
            fetch_redirect_response=False,
        )

    def test_pick_redirects_and_refuses_bad_picks(self) -> None:
        self.client.force_login(self.author)
        url = reverse("admin_soulfray_builder_pick")
        resp = self.client.get(url, {"pk": self.tearing.pk})
        self.assertEqual(
            resp["Location"], reverse("admin_soulfray_builder", args=[self.tearing.pk])
        )
        self.assertEqual(self.client.get(url).status_code, 400)
        self.assertEqual(self.client.get(url, {"pk": "999999"}).status_code, 400)
        self.assertEqual(self.client.get(url, {"pk": self.numb.pk}).status_code, 400)


class ObjectToolTest(SoulfrayPageTestCase):
    def test_a_soulfray_stage_change_form_links_the_builder(self) -> None:
        self.client.force_login(self.author)
        body = self.client.get(
            reverse("admin:arxii_conditionstage_change", args=[self.tearing.pk])
        ).content.decode()
        self.assertIn("Open in Soulfray Stage Builder", body)
        self.assertIn(reverse("admin_soulfray_builder", args=[self.tearing.pk]), body)

    def test_another_conditions_stage_does_not(self) -> None:
        self.client.force_login(self.author)
        body = self.client.get(
            reverse("admin:arxii_conditionstage_change", args=[self.numb.pk])
        ).content.decode()
        self.assertNotIn("Open in Soulfray Stage Builder", body)


class NoStagesIndexTest(TestCase):
    def test_index_with_no_soulfray_stages_returns_to_the_workbench(self) -> None:
        self.client.force_login(_superuser("sfnostages"))
        resp = self.client.get(reverse("admin_soulfray_builder_index"))
        self.assertEqual(resp["Location"], reverse("admin_authoring"))


class NoConfigGetTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.author = _superuser("sfnoconfig")
        PlayerData.objects.create(
            account=cls.author, contributor=ContentContributorFactory(name="No Config Writer")
        )
        cls.ladder = build_ladder()

    def test_page_renders_and_says_the_config_is_missing(self) -> None:
        self.client.force_login(self.author)
        resp = self.client.get(
            reverse("admin_soulfray_builder", args=[self.ladder.stage("Tearing").pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("No Soulfray config exists", resp.content.decode())


class SoulfrayBuilderStylingTest(SoulfrayPageTestCase):
    """Every rule the page's layout needs must REACH the page (#3667).

    The ``BuilderStylingTest`` pattern: name the stylesheets, then require a rule
    in reachable CSS for every class token the templates emit. A class name in the
    markup proves nothing; ``responsive.css`` mentions admin's own class names
    inside media queries.
    """

    REQUIRED_STYLESHEETS = ("admin/css/base.css", "admin/css/forms.css", "admin/css/widgets.css")
    REQUIRED_SCRIPTS = ("admin/js/builder_formsets.js",)
    ADMIN_PROVIDED_CLASSES = frozenset(
        {
            "module",
            "aligned",
            "description",
            "help",
            "errornote",
            "breadcrumbs",
            "submit-row",
            "button",
            "default",
            "tuning-panel",
            "tuning-table",
        }
    )

    def _body(self) -> str:
        resp = self._get(self.fraying)
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()

    def test_the_page_links_the_stylesheets_its_layout_needs(self) -> None:
        linked = stylesheet_hrefs(self._body())
        missing = [s for s in self.REQUIRED_STYLESHEETS if not any(h.endswith(s) for h in linked)]
        self.assertFalse(missing, f"the page does not link {missing}. Linked: {linked}")

    def test_the_page_links_the_shared_builder_formsets_script(self) -> None:
        srcs = re.findall(r'<script[^>]*\bsrc="([^"]+)"', self._body())
        for script in self.REQUIRED_SCRIPTS:
            self.assertTrue(any(src.endswith(script) for src in srcs), srcs)

    def test_the_two_column_shell_and_kill_rows_have_rules(self) -> None:
        css = reachable_css(self._body())
        for rule in (".sf-columns", "grid-template-columns", ".sf-row--kill", ".sf-check--warn"):
            self.assertIn(rule, css)

    def test_every_class_the_page_emits_has_a_rule_that_reaches_the_page(self) -> None:
        template_dir = Path(__file__).resolve().parents[2] / "templates/admin/soulfray_builder"
        emitted: set[str] = set()
        for path in sorted(template_dir.glob("*.html")):
            emitted |= emitted_classes(path)
        css = reachable_css(self._body())
        undefined = sorted(
            token for token in emitted - self.ADMIN_PROVIDED_CLASSES if f".{token}" not in css
        )
        self.assertFalse(undefined, f"class hooks with no CSS rule reaching the page: {undefined}")
