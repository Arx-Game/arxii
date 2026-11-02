"""The Missing combat content page (#4906, slice 4 of #4843), through the test client.

A superuser opens it from the Combat roles panel and sees one row per open flag, each
flagged row linked to the page that fixes it; a clear flag has no row.
"""

from __future__ import annotations

import html
from html.parser import HTMLParser
from pathlib import Path
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from web.admin.tests.test_distinction_builder import emitted_classes, reachable_css
from world.covenants.factories import (
    CovenantRoleFactory,
    VowFocusPickFactory,
    VowStatScalingFactory,
)


class CombatContentPageCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        user_model = get_user_model()
        cls.root = user_model.objects.create_superuser(
            username="combat-content-root", email="combat-content@example.com", password="x"
        )
        cls.staff = user_model.objects.create_user(
            username="combat-content-staff", password="x", is_staff=True
        )

    def get(self) -> str:
        self.client.force_login(self.root)
        response = self.client.get(reverse("admin_combat_content"))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    @staticmethod
    def flag_rows(body: str) -> list[str]:
        tbody = re.search(r"<tbody>(.*?)</tbody>", body, re.DOTALL)
        if tbody is None:
            return []
        return [
            " ".join(re.sub(r"<[^>]+>", " ", row).split())
            for row in re.findall(r"<tr>(.*?)</tr>", tbody.group(1), re.DOTALL)
        ]


class CombatContentPageTest(CombatContentPageCase):
    def test_non_superuser_staff_are_refused(self) -> None:
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("admin_combat_content")).status_code, 403)

    def test_nothing_open_reads_nothing_is_flagged(self) -> None:
        body = self.get()
        self.assertIn("Nothing is flagged.", body)
        self.assertNotIn("<tbody>", body)

    def test_title_breadcrumb_and_heading(self) -> None:
        body = self.get()
        self.assertIn("<h1>Missing combat content</h1>", body)
        crumbs = " ".join(
            html.unescape(
                re.sub(
                    r"<[^>]+>",
                    " ",
                    re.search(r'<div class="breadcrumbs">(.*?)</div>', body, re.DOTALL).group(1),
                )
            ).split()
        )
        self.assertEqual(crumbs, "Home › Ops › Required content › Combat roles")
        self.assertIn(f'href="{reverse("admin_ops")}"', body)
        self.assertIn("flags only, nothing blocked", body)

    def test_open_flags_list_their_rows_and_link_each_to_its_fix_page(self) -> None:
        warden = CovenantRoleFactory(name="Warden")
        aegis = CovenantRoleFactory(name="Aegis")
        fulmination = CovenantRoleFactory(name="Fulmination")
        VowFocusPickFactory(covenant_role=fulmination, name="Under Open Sky")
        kept = VowFocusPickFactory(covenant_role=fulmination, name="Arcing Charge")
        VowStatScalingFactory(covenant_role=fulmination, focus_pick=kept)

        body = self.get()
        self.assertEqual(
            self.flag_rows(body),
            [
                "Vow with no picks Aegis vow page",
                "Warden vow page",
                "Pick with a blank payload Under Open Sky (Fulmination) vow page",
            ],
        )
        for role in (warden, aegis):
            self.assertIn(
                f'<a href="{reverse("admin_vow_builder", args=[role.pk])}" '
                f'aria-label="vow page: {role.name}">vow page</a>',
                body,
            )
        self.assertIn(
            f'<a href="{reverse("admin_vow_builder", args=[fulmination.pk])}" '
            'aria-label="vow page: Under Open Sky (Fulmination)">vow page</a>',
            body,
        )
        # Every page a flagged row links to opens.
        for href in re.findall(r'<td><a href="([^"]+)" aria-label=', body):
            with self.subTest(href=href):
                self.assertEqual(self.client.get(href).status_code, 200)


class _ClassCollector(HTMLParser):
    """Every class token inside ``#combat-content-root``."""

    VOID = frozenset({"input", "br", "hr", "img", "link", "meta", "col", "source", "wbr"})

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.classes: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        element_id = attributes.get("id") or ""
        if element_id == "combat-content-root" or "combat-content-root" in self.stack:
            self.classes |= set((attributes.get("class") or "").split())
        if tag not in self.VOID:
            self.stack.append(element_id)

    def handle_endtag(self, tag: str) -> None:
        if tag not in self.VOID and self.stack:
            self.stack.pop()


class CombatContentStylingTest(CombatContentPageCase):
    """Every class the page emits has a rule reaching the page (#3667's rule, for #4906)."""

    def _undefined(self, classes: set[str], css: str) -> list[str]:
        return sorted(token for token in classes if not re.search(rf"\.{re.escape(token)}\b", css))

    def test_every_class_under_the_root_has_a_rule_reaching_the_page(self) -> None:
        CovenantRoleFactory(name="Warden")
        for state, body in {"with flags": self.get()}.items():
            with self.subTest(state=state):
                collector = _ClassCollector()
                collector.feed(body)
                self.assertTrue(collector.classes)
                self.assertEqual(self._undefined(collector.classes, reachable_css(body)), [])

    def test_every_class_the_template_emits_has_a_rule_reaching_the_page(self) -> None:
        template = (
            Path(__file__).resolve().parents[2] / "templates/admin/tuning/combat_content.html"
        )
        css = reachable_css(self.get())
        self.assertEqual(self._undefined(emitted_classes(template), css), [])
