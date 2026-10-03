"""The Soulfray Stage Builder page: read side, reachability, styling (#4089)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field as dc_field
from html.parser import HTMLParser
from pathlib import Path
import re

from django.contrib import admin
from django.contrib.staticfiles import finders
from django.db import connection
from django.http import QueryDict
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
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
    build_ladder,
    form_values,
    make_superuser,
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
from world.conditions.factories import (
    ConditionStageFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
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
        cls.unlinked = make_superuser("sfunlinked")
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
    def test_renders_inside_the_admin_chrome(self) -> None:
        """The view merges ``admin.site.each_context``: site header and user tools."""
        self.client.force_login(self.author)
        url = reverse("admin_soulfray_builder", args=[self.tearing.pk])
        body = self.client.get(url).content.decode()
        self.assertIn(str(admin.site.site_header), body)
        self.assertIn('id="user-tools"', body)
        # The app-list sidebar stays off: it would squeeze the builder's two columns.
        self.assertNotIn('id="nav-sidebar"', body)

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
        self.assertIn("Spin the wheel: if any option for a roll result is ticked", body)

    def test_shared_rows_name_their_pool_and_own_rows_say_this_stage(self) -> None:
        body = self._get(self.fraying).content.decode()
        self.assertIn('value="Fraying Failure"', body)
        self.assertIn("Soulfray - common", body)
        self.assertIn("this stage", body)
        self.assertIn("Apply Condition, self, Shaken sev 1", body)

    def test_shared_rows_render_read_only(self) -> None:
        """Ruling RF-1: a shared row's text is text, its boxes disabled, no effect editor."""
        resp = self._get(self.fraying)
        body = resp.content.decode()
        self.assertIn("common Success", body)
        self.assertNotIn('value="common Success"', body)
        shared = Consequence.objects.get(label="common Success")
        self.assertNotIn(f'id="effects-e{shared.pk}"', body)
        self.assertIn(f'id="effects-e{self.fraying_failure.pk}"', body)
        index = next(
            i
            for i, row in enumerate(resp.context["forms"].table)
            if row.consequence.pk == shared.pk
        )
        for name in ("character_loss", "theater"):
            self.assertRegex(body, rf'<input[^>]*name="rows-{index}-{name}"[^>]*disabled')

    def test_the_new_pool_name_shows_only_for_a_stage_with_no_pool(self) -> None:
        pooled = self._get(self.fraying).content.decode()
        self.assertIn('<span id="new-pool-name" hidden>', pooled)
        unpooled = self._get(self.tearing).content.decode()
        self.assertIn('<span id="new-pool-name">', unpooled)
        self.assertIn('value="Soulfray - Tearing"', unpooled)
        # Hidden is not dropped: the name still posts, so "New pool" works unscripted.
        self.assertEqual(form_values(pooled)["pool-new_name"], ["Soulfray - Fraying"])

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

    def test_a_saved_rows_prefetched_effects_bind_and_save_on_post(self) -> None:
        prefix = f"e{self.fraying_failure.pk}"
        data = self._posted({f"{prefix}-0-condition_severity": ["3"]})
        effects = build_forms(data, self.fraying, self.config, None).effects[
            self.fraying_failure.pk
        ]
        self.assertTrue(effects.is_valid(), effects.errors)
        self.assertEqual(len(effects.forms), 1)
        effect = self.fraying_failure.effects.get()
        self.assertEqual(effects.forms[0].instance.pk, effect.pk)
        effects.save()
        effect.refresh_from_db()
        self.assertEqual(effect.condition_severity, 3)

    def test_a_new_row_posted_without_an_effects_management_form_has_no_effects(self) -> None:
        index = len(consequence_table(self.fraying_pool))
        data = self._posted({"rows-TOTAL_FORMS": [str(index + 1)]})
        effects = build_forms(data, self.fraying, self.config, None).new_effects[index]
        self.assertTrue(effects.is_valid(), effects.errors)
        self.assertEqual(effects.forms, [])


class BuilderGetQueryCountTest(SoulfrayBuilderTestCase):
    """A GET's query count does not grow with the stage's rows or their effects.

    Each row's "Roll result" select, each effect form's damage-type select and
    each saved row's effects formset used to query per row. Ripping (2 rows) and
    Sundering (5 rows) each carry one damage effect per row, so any per-row
    query makes the two counts differ.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        PlayerData.objects.create(
            account=cls.author, contributor=ContentContributorFactory(name="Count Writer")
        )
        SoulfrayConfigFactory()
        cls.small = cls.ladder.stage("Ripping")
        cls.large = cls.ladder.stage("Sundering")
        stock(cls.small, cls.ladder, tiers=("Failure", "Success"))
        stock(cls.large, cls.ladder)
        damage = DamageTypeFactory()
        for consequence in Consequence.objects.filter(
            pool_entries__pool__condition_stages__in=[cls.small, cls.large]
        ):
            ConsequenceEffectFactory(
                consequence=consequence,
                effect_type=EffectType.DEAL_DAMAGE,
                damage_amount=4,
                damage_type=damage,
            )

    def _count(self, stage) -> int:
        url = reverse("admin_soulfray_builder", args=[stage.pk])
        self.client.get(url)  # warm sessions, content types and the config singleton
        with CaptureQueriesContext(connection) as queries:
            resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("Link a contributor first.", resp.content.decode())
        return len(queries)

    def test_five_rows_cost_what_two_rows_cost(self) -> None:
        self.client.force_login(self.author)
        self.assertEqual(self._count(self.large), self._count(self.small))


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
        self.client.force_login(make_superuser("sfnostages"))
        resp = self.client.get(reverse("admin_soulfray_builder_index"))
        self.assertEqual(resp["Location"], reverse("admin_authoring"))


class NoConfigGetTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.author = make_superuser("sfnoconfig")
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


_VOID_TAGS = frozenset({"area", "br", "col", "hr", "img", "input", "link", "meta", "source", "wbr"})
_FIELD_TAGS = frozenset({"input", "select", "textarea"})


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    parent: _Node | None = None
    children: list[_Node] = dc_field(default_factory=list)

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def walk(self) -> Iterator[_Node]:
        for child in self.children:
            yield child
            yield from child.walk()

    def inside(self, css_class: str) -> bool:
        node = self.parent
        while node is not None:
            if css_class in node.classes:
                return True
            node = node.parent
        return False


class _Tree(HTMLParser):
    """Just enough of a DOM to read which element sits inside which (no bs4 here)."""

    def __init__(self) -> None:
        super().__init__()
        self.root = _Node("root", {})
        self._open = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, {k: v or "" for k, v in attrs}, parent=self._open)
        self._open.children.append(node)
        if tag not in _VOID_TAGS:
            self._open = node

    def handle_endtag(self, tag: str) -> None:
        node = self._open
        while node is not None and node.tag != tag:
            node = node.parent
        if node is not None and node.parent is not None:
            self._open = node.parent


def _tree(body: str) -> _Node:
    parser = _Tree()
    parser.feed(body)
    return parser.root


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

    def test_every_form_row_puts_its_label_beside_its_field(self) -> None:
        """F1: admin's aligned layout, the markup the threshold change form draws.

        ``forms.css`` lays a row out as a label column beside the field only when the
        label and the field share a ``.flex-container`` (``display: flex``) and the help
        line sits outside it. This reads the rendered page's tree for that shape, and
        the forms.css rules that turn it into a row, which the page links.
        """
        body = self._body()
        rows = [
            node
            for node in _tree(body).walk()
            if "form-row" in node.classes and node.inside("aligned")
        ]
        self.assertGreaterEqual(len(rows), 11)
        for row in rows:
            flex = next((n for n in row.walk() if "flex-container" in n.classes), None)
            self.assertIsNotNone(flex, f"a form row with no .flex-container: {row.attrs}")
            self.assertEqual(flex.children[0].tag, "label")
            fields = [
                n for n in flex.walk() if n.tag in _FIELD_TAGS and n.attrs.get("type") != "hidden"
            ]
            self.assertTrue(fields, f"no field beside {flex.children[0].attrs}")
            for help_line in (n for n in row.walk() if "help" in n.classes):
                self.assertFalse(help_line.inside("flex-container"))
        forms_css = Path(finders.find("admin/css/forms.css")).read_text()
        self.assertRegex(forms_css, r"\.flex-container \{\s*display: flex;")
        self.assertRegex(forms_css, r"\.aligned label \{[^}]*width: 160px;")
        self.assertRegex(forms_css, r"form \.aligned div\.help \{[^}]*margin-left: 160px;")
        css = reachable_css(body)
        self.assertRegex(css, r"\.aligned \.sf-field \{[^}]*display: flex;")
        self.assertRegex(css, r"\.aligned \.sf-field label \{[^}]*width: auto;")

    def test_the_pool_and_its_parent_share_one_row(self) -> None:
        rows = [n for n in _tree(self._body()).walk() if "form-row" in n.classes]
        names = [{f.attrs.get("name") for f in row.walk() if f.tag in _FIELD_TAGS} for row in rows]
        self.assertIn({"pool-pool", "pool-new_name", "pool-parent"}, names)

    def test_one_h1_names_the_stage(self) -> None:
        """F4: the content area has one h1, the view's title (the branding h1 aside)."""
        h1s = re.findall(r"<h1>(.*?)</h1>", self._body(), flags=re.DOTALL)
        self.assertEqual(h1s, ["Fraying - Soulfray Stage Builder"])

    def test_lists_live_lines_and_weight_inputs_have_their_rules(self) -> None:
        """F2, F3, F5: base.css squares every ``ul > li``; the demo marks live lines."""
        css = reachable_css(self._body())
        self.assertRegex(css, r"\.sf-checks > li \{ list-style: none; \}")
        self.assertRegex(css, r"\.sf-effects > li,")
        self.assertRegex(css, r'\.sf-live::before \{\s*content: "\\25CF  live";')
        self.assertRegex(css, r"\.sf-table td\.sf-num input \{ width: 4rem; \}")

    def test_a_ticked_can_kill_box_is_drawn_in_the_error_colour(self) -> None:
        """F7: the demo draws a lethal row's ticked Can kill box red, not browser blue."""
        css = reachable_css(self._body())
        self.assertRegex(
            css,
            r'\.sf-table input\[name\$="-character_loss"\] \{ accent-color: var\(--error-fg\); \}',
        )

    def test_the_effect_toggle_sits_on_its_own_line(self) -> None:
        """F9: "+ effect" is a block under the effect list, never run on after "no effect"."""
        css = reachable_css(self._body())
        self.assertRegex(css, r"\.sf-effect-toggle \{\s*display: block;")

    def test_each_effect_editor_is_a_full_width_row_its_toggle_opens(self) -> None:
        """F8: the editor sits in a colspan row under its consequence, never in the
        narrow Effects cell, so opening it cannot scroll the table sideways."""
        tree = _tree(self._body())
        toggles = [n for n in tree.walk() if "sf-effect-toggle" in n.classes]
        self.assertTrue(toggles)
        rows = {n.attrs.get("id"): n for n in tree.walk() if "sf-effect-editor-row" in n.classes}
        for toggle in toggles:
            if toggle.inside("sf-effect-editor-row") or toggle.parent is None:
                continue
            editor = rows[toggle.attrs["aria-controls"]]
            self.assertEqual(editor.tag, "tr")
            self.assertIn("hidden", editor.attrs)
            self.assertEqual(editor.children[0].attrs.get("colspan"), "8")
            self.assertTrue(
                any("sf-effect-editor" in n.classes for n in editor.walk()),
                "the editor row holds the editor",
            )
