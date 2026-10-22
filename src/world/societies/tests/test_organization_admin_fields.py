"""The Organization admin shows every house field; covert is its own checkbox (#4570)."""

from html.parser import HTMLParser
import re

from django.test import TestCase
from django.urls import reverse

from evennia_extensions.factories import AccountFactory
from world.roster.factories import FamilyFactory
from world.societies.factories import OrganizationFactory, OrganizationTypeFactory


class OrganizationAdminFieldsTests(TestCase):
    def setUp(self) -> None:
        staff = AccountFactory(username="admin_org_fields", is_staff=True, is_superuser=True)
        self.client.force_login(staff)

    def _page(self, url: str) -> str:
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_the_add_form_has_the_covert_checkbox(self) -> None:
        page = self._page(reverse("admin:arxii_organization_add"))
        self.assertIn('name="is_covert"', page)
        self.assertIn('type="checkbox"', page)

    def test_the_change_page_shows_the_family_and_the_house_fields(self) -> None:
        family = FamilyFactory(name="Katta")
        org = OrganizationFactory(name="House Katta", family=family, words="Nothing is forgotten.")
        page = self._page(reverse("admin:arxii_organization_change", args=[org.pk]))
        for field in ("family", "parent_org", "house_state", "published_at_0", "words", "colors"):
            self.assertIn(f'name="{field}"', page)
        self.assertIn("Nothing is forgotten.", page)
        self.assertRegex(page, rf'<option value="{family.pk}" selected>Katta</option>')

    def test_the_covert_checkbox_saves_onto_the_organization(self) -> None:
        org = OrganizationFactory(name="The Masquers")
        url = reverse("admin:arxii_organization_change", args=[org.pk])
        self.assertNotIn('id="id_is_covert" checked', self._page(url))
        response = self.client.post(url, {**self._form_data(org), "is_covert": "on"})
        body = response.content.decode()
        errors = re.findall(r'<ul class="errorlist[^"]*">(.*?)</ul>', body, re.DOTALL)
        self.assertEqual(response.status_code, 302, errors or body[:300])
        org.refresh_from_db()
        self.assertTrue(org.is_covert)
        self.assertIn('id="id_is_covert" checked', self._page(url))

    def _form_data(self, org) -> dict[str, str]:
        """Every field the rendered change form would post, inline rows included."""
        page = self._page(reverse("admin:arxii_organization_change", args=[org.pk]))
        form = _FormScraper()
        form.feed(page)
        return {**form.data, "_continue": "1"}

    def test_the_type_form_has_reach_and_no_covert_flag(self) -> None:
        kind = OrganizationTypeFactory(name="tradition")
        page = self._page(reverse("admin:arxii_organizationtype_change", args=[kind.pk]))
        self.assertIn('name="reach"', page)
        self.assertNotIn('name="is_covert"', page)


class _FormScraper(HTMLParser):
    """Collects what a browser would submit from the change form: every named input,
    the selected option of every select, and every textarea."""

    def __init__(self) -> None:
        super().__init__()
        self.data: dict[str, str] = {}
        self._select: str | None = None
        self._textarea: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        name = a.get("name")
        if tag == "input" and name:
            kind = a.get("type", "text")
            if kind in ("submit", "button", "file"):
                return
            if kind in ("checkbox", "radio") and "checked" not in a:
                return
            self.data[name] = a.get("value") or ("on" if kind == "checkbox" else "")
        elif tag == "select" and name:
            self._select = name
            self.data.setdefault(name, "")
        elif tag == "option" and self._select and "selected" in a:
            self.data[self._select] = a.get("value") or ""
        elif tag == "textarea" and name:
            self._textarea, self._text = name, []

    def handle_data(self, data: str) -> None:
        if self._textarea:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "select":
            self._select = None
        elif tag == "textarea" and self._textarea:
            self.data[self._textarea] = "".join(self._text)
            self._textarea = None
