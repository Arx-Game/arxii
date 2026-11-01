"""The combo map pages through the test client (#4891, slice 3 of #4843).

Staff open one property or one condition and see what sets it and what reads it, each
row linked to its edit page, with a "Set by nothing" or "Read by nothing" mark where a
side is empty. Read only: staff who can view the model may open it.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from web.admin.tests.test_combo_map_live import ComboMapLiveCase
from web.admin.tests.test_distinction_builder import (
    emitted_classes,
    reachable_css,
    stylesheet_hrefs,
)
from world.magic.factories import TechniqueAppliedConditionFactory, TechniqueFactory
from world.mechanics.factories import PrerequisiteFactory


class ComboMapPageCase(ComboMapLiveCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        user_model = get_user_model()
        cls.staff = user_model.objects.create_superuser(
            username="combo-map-staff", email="combo-map@example.com", password="x"
        )
        cls.viewer = user_model.objects.create_user(
            username="combo-map-viewer", password="x", is_staff=True
        )
        cls.viewer.user_permissions.add(
            Permission.objects.get(codename="view_property"),
            Permission.objects.get(codename="view_conditiontemplate"),
        )
        cls.outsider = user_model.objects.create_user(
            username="combo-map-outsider", password="x", is_staff=True
        )

    def property_url(self, pk: int | None = None) -> str:
        return reverse("admin_combo_map_property", args=[pk or self.indulgence.pk])

    def condition_url(self, pk: int | None = None) -> str:
        return reverse("admin_combo_map_condition", args=[pk or self.tipsy.pk])

    def get(self, url: str) -> str:
        self.client.force_login(self.staff)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()


class PropertyPageTest(ComboMapPageCase):
    def test_the_property_page_lists_carriers_setters_and_readers(self) -> None:
        body = self.get(self.property_url())
        self.assertIn("Conditions carrying it", body)
        self.assertIn(
            f'href="{self.condition_url(self.charmed.pk)}">Charmed</a> (stage 2 only)', body
        )
        technique_url = reverse("admin:arxii_technique_change", args=[self.unbound.pk])
        self.assertIn(f'<a href="{technique_url}">{self.unbound_label}</a>', body)
        edit_url = reverse("admin:arxii_property_change", args=[self.indulgence.pk])
        self.assertIn(f'<a href="{edit_url}">Edit property</a>', body)
        self.assertIn("Tipsy on self", body)
        self.assertIn("Charmed on the pressed group", body)
        prerequisite_url = reverse("admin:arxii_prerequisite_change", args=[self.prerequisite.pk])
        self.assertIn(f'<a href="{prerequisite_url}">Must be indulgent</a>', body)
        # Smitten carries the property and nothing lands it.
        self.assertRegex(body, r"<td>Smitten</td>\s*<td colspan=\"2\"><span[^>]*>Set by nothing")
        self.assertNotIn("Read by nothing", body)
        crumbs = re.search(r'<div class="breadcrumbs">(.*?)</div>', body, re.DOTALL).group(1)
        self.assertEqual(
            re.sub(r"<[^>]+>|\s+", " ", crumbs).split(),
            [
                "Home",
                "&rsaquo;",
                "Combat",
                "roles",
                "&rsaquo;",
                "Combo",
                "map",
                "&rsaquo;",
                "Indulgence",
            ],
        )

    def test_an_untouched_property_is_marked_both_ways(self) -> None:
        body = self.get(self.property_url(self.lonely.pk))
        self.assertIn("Set by nothing", body)
        self.assertIn("Read by nothing", body)

    def test_unknown_property_is_404(self) -> None:
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.property_url(999999)).status_code, 404)

    def test_query_count_stays_flat_as_sources_grow(self) -> None:
        self.client.force_login(self.staff)
        self.client.get(self.property_url())  # warm the session and site caches
        with CaptureQueriesContext(connection) as before:
            self.client.get(self.property_url())
        for n in range(3):
            TechniqueAppliedConditionFactory(
                technique=TechniqueFactory(name=f"More {n}"), condition=self.tipsy
            )
            PrerequisiteFactory(name=f"Also indulgent {n}", property=self.indulgence)
        with self.assertNumQueries(len(before.captured_queries)):
            self.client.get(self.property_url())


class ConditionPageTest(ComboMapPageCase):
    def test_the_condition_page_groups_readers_by_itself_then_each_property(self) -> None:
        body = self.get(self.condition_url())
        self.assertIn("Properties it carries", body)
        self.assertIn(f'href="{self.property_url()}">Indulgence</a>', body)
        headings = re.findall(r'<th scope="colgroup" colspan="3">([^<]+)</th>', body)
        self.assertEqual(headings, ["Tipsy", "Indulgence"])
        target_url = reverse("admin:arxii_modifiertarget_change", args=[self.against_tipsy.pk])
        self.assertIn(f'<a href="{target_url}">Against the tipsy</a>', body)

    def test_a_condition_nothing_lands(self) -> None:
        body = self.get(self.condition_url(self.signed.pk))
        self.assertIn("Set by nothing", body)
        self.assertNotIn("Read by nothing", body)  # the interaction reads it


class GateTest(ComboMapPageCase):
    def test_staff_with_view_permission_can_open_both(self) -> None:
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.property_url()).status_code, 200)
        self.assertEqual(self.client.get(self.condition_url()).status_code, 200)

    def test_staff_without_view_permission_are_refused(self) -> None:
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.property_url()).status_code, 403)
        self.assertEqual(self.client.get(self.condition_url()).status_code, 403)
        pick = reverse("admin_combo_map_property_pick")
        self.assertEqual(self.client.get(pick, {"pk": self.indulgence.pk}).status_code, 403)

    def test_the_page_is_get_only(self) -> None:
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(self.property_url()).status_code, 405)


class ChangeFormLinkTest(ComboMapPageCase):
    def test_property_and_condition_change_forms_link_to_their_combo_map(self) -> None:
        cases = (
            (
                reverse("admin:arxii_property_change", args=[self.indulgence.pk]),
                self.property_url(),
            ),
            (
                reverse("admin:arxii_conditiontemplate_change", args=[self.tipsy.pk]),
                self.condition_url(),
            ),
        )
        for change_url, map_url in cases:
            with self.subTest(change_url=change_url):
                body = self.get(change_url)
                self.assertIn(
                    f'<a href="{map_url}" class="workbench-open-link">Combo map</a>', body
                )
                self.assertEqual(self.client.get(map_url).status_code, 200)

    def test_other_change_forms_carry_no_combo_map_link(self) -> None:
        body = self.get(reverse("admin:arxii_technique_change", args=[self.unbound.pk]))
        self.assertNotIn(">Combo map</a>", body)


class PickTest(ComboMapPageCase):
    def test_pick_routes_redirect_to_the_page(self) -> None:
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("admin_combo_map_property_pick"), {"pk": self.indulgence.pk}
        )
        self.assertRedirects(response, self.property_url())
        response = self.client.get(reverse("admin_combo_map_condition_pick"), {"pk": self.tipsy.pk})
        self.assertRedirects(response, self.condition_url())

    def test_pick_routes_refuse_a_missing_or_unknown_pk(self) -> None:
        self.client.force_login(self.staff)
        for name in ("admin_combo_map_property_pick", "admin_combo_map_condition_pick"):
            for params in ({}, {"pk": "abc"}, {"pk": 999999}):
                with self.subTest(route=name, params=params):
                    self.assertEqual(self.client.get(reverse(name), params).status_code, 400)


class _ClassCollector(HTMLParser):
    """Every class token inside ``#combo-map-root`` and the ``<h1>`` count in ``#content``."""

    VOID = frozenset({"input", "br", "hr", "img", "link", "meta", "col", "source", "wbr"})

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[tuple[str, str]] = []
        self.classes: set[str] = set()
        self.content_h1 = 0

    def _inside(self, element_id: str) -> bool:
        return any(tag_id == element_id for _, tag_id in self.stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        element_id = attributes.get("id") or ""
        if element_id == "combo-map-root" or self._inside("combo-map-root"):
            self.classes |= set((attributes.get("class") or "").split())
        if tag == "h1" and self._inside("content"):
            self.content_h1 += 1
        if tag not in self.VOID:
            self.stack.append((tag, element_id))

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                return


class ComboMapStylingTest(ComboMapPageCase):
    """Every class the page emits has a rule reaching the page (#3667's rule, for #4891).

    Read off the rendered page with and without gap chips, and off the templates, so a
    class only one state emits is checked too.
    """

    REQUIRED_STYLESHEETS = ("admin/css/base.css", "admin/css/forms.css", "admin/css/widgets.css")

    def _states(self) -> dict[str, str]:
        return {
            "with setters and readers": self.get(self.condition_url()),
            "with gap chips": self.get(self.property_url(self.lonely.pk)),
            "property with a stage carrier": self.get(self.property_url()),
        }

    def test_the_page_links_forms_css_and_widgets_css(self) -> None:
        linked = stylesheet_hrefs(self.get(self.property_url()))
        missing = [s for s in self.REQUIRED_STYLESHEETS if not any(h.endswith(s) for h in linked)]
        self.assertEqual(missing, [], f"Linked: {linked}")

    def test_every_class_under_the_root_has_a_rule_reaching_the_page(self) -> None:
        for state, body in self._states().items():
            with self.subTest(state=state):
                collector = _ClassCollector()
                collector.feed(body)
                css = reachable_css(body)
                undefined = sorted(
                    token
                    for token in collector.classes
                    if not re.search(rf"\.{re.escape(token)}\b", css)
                )
                self.assertEqual(undefined, [], "class hooks with no CSS rule reaching the page")
                self.assertEqual(collector.content_h1, 1)

    def test_every_class_the_templates_emit_has_a_rule_reaching_the_page(self) -> None:
        css = reachable_css(self.get(self.property_url()))
        template_dir = Path(__file__).resolve().parents[2] / "templates/admin/combo_map"
        emitted: set[str] = set()
        for path in sorted(template_dir.glob("*.html")):
            emitted |= emitted_classes(path)
        undefined = sorted(
            token for token in emitted if not re.search(rf"\.{re.escape(token)}\b", css)
        )
        self.assertEqual(undefined, [], "class hooks with no CSS rule reaching the page")
