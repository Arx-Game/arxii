"""The Organization admin shows every house field; covert is its own checkbox (#4570)."""

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
        org = OrganizationFactory(name="Katta", family=family, words="Nothing is forgotten.")
        page = self._page(reverse("admin:arxii_organization_change", args=[org.pk]))
        for field in ("family", "parent_org", "house_state", "published_at_0", "words", "colors"):
            self.assertIn(f'name="{field}"', page)
        self.assertIn("Nothing is forgotten.", page)

    def test_the_covert_checkbox_saves_onto_the_organization(self) -> None:
        org = OrganizationFactory(name="The Masquers")
        page = self._page(reverse("admin:arxii_organization_change", args=[org.pk]))
        self.assertNotIn('id="id_is_covert" checked', page)
        org.is_covert = True
        org.save(update_fields=["is_covert"])
        page = self._page(reverse("admin:arxii_organization_change", args=[org.pk]))
        self.assertIn('id="id_is_covert" checked', page)

    def test_the_type_form_has_reach_and_no_covert_flag(self) -> None:
        kind = OrganizationTypeFactory(name="tradition")
        page = self._page(reverse("admin:arxii_organizationtype_change", args=[kind.pk]))
        self.assertIn('name="reach"', page)
        self.assertNotIn('name="is_covert"', page)
