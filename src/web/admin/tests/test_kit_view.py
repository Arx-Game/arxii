"""The kit view page through the test client (#4918, slice 5 of #4843).

Staff open one character and read its techniques with what the vow adds, its chosen
focus picks against the budget, and its path, gift, vow and defense. Read only: staff
who can view character sheets may open it. The character is ``KitLiveCase``'s.
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

from web.admin.tests.test_distinction_builder import (
    emitted_classes,
    reachable_css,
    stylesheet_hrefs,
)
from web.admin.tests.test_kit_view_live import KitLiveCase, _know, _technique
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import (
    CharacterVowFocusPickFactory,
    VowAddedEffectFactory,
    VowFocusPickFactory,
    engage_vow_with_thread,
)
from world.covenants.models import CharacterVowFocusPick
from world.magic.constants import TechniqueFunction


class KitPageCase(KitLiveCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        user_model = get_user_model()
        cls.staff = user_model.objects.create_superuser(
            username="kit-view-staff", email="kit-view@example.com", password="x"
        )
        cls.viewer = user_model.objects.create_user(
            username="kit-view-viewer", password="x", is_staff=True
        )
        cls.viewer.user_permissions.add(Permission.objects.get(codename="view_charactersheet"))
        cls.outsider = user_model.objects.create_user(
            username="kit-view-outsider", password="x", is_staff=True
        )

    def url(self, pk: int | None = None) -> str:
        return reverse("admin_kit_view", args=[pk or self.sheet.pk])

    def get(self, url: str) -> str:
        self.client.force_login(self.staff)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()


class KitPageTest(KitPageCase):
    def test_the_techniques_module_shows_base_and_what_the_vow_adds(self) -> None:
        body = self.get(self.url())
        self.assertIn("Techniques, with what the vow adds", body)
        self.assertIn("Vow adds (level 2)", body)
        bolt_url = reverse("admin:arxii_technique_change", args=[self.bolt.pk])
        self.assertIn(f'<a href="{bolt_url}">Bolt</a><span class="kv-sub">Strike</span>', body)
        self.assertIn(
            f'<span class="kv-group">Base:</span> {self.base.cached_effect_summary}</p>', body
        )
        self.assertIn(
            f'<span class="kv-group">Spark:</span> {self.on_spark.cached_effect_summary}</p>',
            body,
        )
        self.assertNotIn("Unchosen:", body)
        self.assertIn('<span class="kv-chip kv-mark">unlocks at level 5</span>', body)
        self.assertIn('<span class="kv-chip kv-note">rides Covenant Allies</span>', body)
        self.assertIn("nothing: Tempest adds nothing to Perception", body)

    def test_the_picks_module_marks_a_level_over_budget(self) -> None:
        body = self.get(self.url())
        spark_url = reverse("admin:arxii_vowfocuspick_change", args=[self.spark.pk])
        gale_url = reverse("admin:arxii_vowfocuspick_change", args=[self.gale.pk])
        self.assertIn(
            f'Level 1 &middot; <a href="{gale_url}">Gale</a>, <a href="{spark_url}">Spark</a>',
            body,
        )
        self.assertIn('7 of 4 <span class="kv-chip kv-mark">over budget</span>', body)
        changelist = reverse("admin:arxii_charactervowfocuspick_changelist")
        self.assertIn(
            f'href="{changelist}?q={self.sheet.character.db_key}">Edit chosen picks', body
        )
        self.assertIn(
            f'href="{reverse("admin_vow_builder", args=[self.vow.pk])}">Tempest vow page', body
        )

    def test_the_sheet_module_names_path_gift_vow_and_defense(self) -> None:
        body = self.get(self.url())
        self.assertIn("<td>Tomes &middot; Storms</td>", body)
        vow_url = reverse("admin_vow_builder", args=[self.vow.pk])
        self.assertIn(f'<td><a href="{vow_url}">Tempest</a>, level 2</td>', body)
        self.assertIn("<td>Evasion</td>", body)
        crumbs = re.search(r'<div class="breadcrumbs">(.*?)</div>', body, re.DOTALL).group(1)
        name = self.sheet.character.db_key
        self.assertEqual(
            re.sub(r"<[^>]+>|\s+", " ", crumbs).split(),
            ["Home", "&rsaquo;", "Combat", "roles", "&rsaquo;", "Kit", "view", "&rsaquo;", name],
        )
        self.assertIn(f"<h1>{name}</h1>", body)

    def test_a_character_with_nothing_says_what_is_absent(self) -> None:
        body = self.get(self.url(CharacterSheetFactory().pk))
        self.assertIn("Knows no techniques.", body)
        self.assertIn("No primary vow, so no focus picks.", body)
        self.assertIn("No live vow", body)
        self.assertIn("No path &middot; no gift", body)
        self.assertIn('<th scope="col">Vow adds</th>', body)

    def test_unknown_sheet_is_404(self) -> None:
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url(999999)).status_code, 404)

    def test_query_count_stays_flat_as_the_kit_grows(self) -> None:
        self.client.force_login(self.staff)
        self.client.get(self.url())  # warm the session and site caches
        counts = []
        for techniques, picks in ((1, 1), (6, 4)):
            sheet = CharacterSheetFactory()
            membership = engage_vow_with_thread(
                sheet, self.vow, covenant=self.covenant, thread_level=2
            )
            for index in range(techniques):
                _know(sheet, _technique(f"Page {picks} {index}", TechniqueFunction.STRIKE))
            for index in range(picks):
                pick = VowFocusPickFactory(
                    covenant_role=self.vow, name=f"Page pick {picks} {index}"
                )
                CharacterVowFocusPickFactory(character_role=membership, pick=pick)
                VowAddedEffectFactory(
                    covenant_role=self.vow, function=TechniqueFunction.STRIKE, focus_pick=pick
                )
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get(self.url(sheet.pk)).status_code, 200)
            counts.append(len(queries))
        self.assertEqual(counts[0], counts[1])
        self.assertEqual(counts[1], PAGE_QUERIES)


class GateTest(KitPageCase):
    def test_staff_with_view_permission_can_open_it(self) -> None:
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.url()).status_code, 200)

    def test_staff_without_view_permission_are_refused(self) -> None:
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        pick = reverse("admin_kit_view_pick")
        self.assertEqual(self.client.get(pick, {"pk": self.sheet.pk}).status_code, 403)

    def test_the_page_is_get_only(self) -> None:
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(self.url()).status_code, 405)


class PickTest(KitPageCase):
    def test_the_pick_route_redirects_to_the_page(self) -> None:
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin_kit_view_pick"), {"pk": self.sheet.pk})
        self.assertRedirects(response, self.url())

    def test_the_pick_route_refuses_a_missing_or_unknown_pk(self) -> None:
        self.client.force_login(self.staff)
        for params in ({}, {"pk": "abc"}, {"pk": 999999}):
            with self.subTest(params=params):
                response = self.client.get(reverse("admin_kit_view_pick"), params)
                self.assertEqual(response.status_code, 400)


class ChangeFormLinkTest(KitPageCase):
    def test_the_sheet_and_chosen_pick_change_forms_link_to_the_kit_view(self) -> None:
        choice = CharacterVowFocusPick.objects.filter(pick=self.spark).first()
        for change_url in (
            reverse("admin:arxii_charactersheet_change", args=[self.sheet.pk]),
            reverse("admin:arxii_charactervowfocuspick_change", args=[choice.pk]),
        ):
            with self.subTest(change_url=change_url):
                body = self.get(change_url)
                self.assertIn(
                    f'<a href="{self.url()}" class="workbench-open-link">Kit view</a>', body
                )
        self.assertEqual(self.client.get(self.url()).status_code, 200)

    def test_other_change_forms_carry_no_kit_view_link(self) -> None:
        body = self.get(reverse("admin:arxii_technique_change", args=[self.bolt.pk]))
        self.assertNotIn(">Kit view</a>", body)


class _ClassCollector(HTMLParser):
    """Every class token inside ``#kit-view-root`` and the ``<h1>`` count in ``#content``."""

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
        if element_id == "kit-view-root" or self._inside("kit-view-root"):
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


class KitViewStylingTest(KitPageCase):
    """Every class the page emits has a rule reaching the page (#3667's rule, for #4918).

    Read off the rendered page with a vow and without one, and off the templates, so a
    class only one state emits is checked too.
    """

    def _states(self) -> dict[str, str]:
        return {
            "with a vow": self.get(self.url()),
            "with no vow": self.get(self.url(CharacterSheetFactory().pk)),
        }

    def test_the_page_links_admin_base_css(self) -> None:
        linked = stylesheet_hrefs(self.get(self.url()))
        self.assertTrue(any(href.endswith("admin/css/base.css") for href in linked), linked)

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
        css = reachable_css(self.get(self.url()))
        template_dir = Path(__file__).resolve().parents[2] / "templates/admin/kit_view"
        emitted: set[str] = set()
        for path in sorted(template_dir.glob("*.html")):
            emitted |= emitted_classes(path)
        undefined = sorted(
            token for token in emitted if not re.search(rf"\.{re.escape(token)}\b", css)
        )
        self.assertEqual(undefined, [], "class hooks with no CSS rule reaching the page")


#: The whole request for one primary vow with picks and techniques the vow adds to: the
#: session and user, the sheet, the kit reads (``test_kit_view_live.KIT_QUERIES``, 22) and
#: the admin chrome (``each_context``'s one existence check per config singleton). See
#: ``KitPageTest.test_query_count_stays_flat_as_the_kit_grows``.
PAGE_QUERIES = 74
