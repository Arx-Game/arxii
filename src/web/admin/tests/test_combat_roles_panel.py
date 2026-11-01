"""The Combat roles panel on the admin front page (#4857, slice 1 of #4843).

Staff find every combat role authoring page from the front page; each link opens.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from world.covenants.factories import CombatStyleFactory
from world.covenants.models import VowFocusPickConfig


class CombatRolesPanelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = get_user_model().objects.create_superuser(
            username="combat-roles-staff", email="combat-roles@example.com", password="x"
        )
        CombatStyleFactory()

    def setUp(self) -> None:
        self.client.force_login(self.staff)

    def _links(self) -> list:
        resp = self.client.get(reverse("admin:index"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="combat-roles-module"')
        return resp.context["combat_roles_links"]

    def test_every_link_on_the_panel_opens(self) -> None:
        links = self._links()
        labels = [link.label for link in links]
        self.assertEqual(
            labels,
            [
                "Covenant roles",
                "Vow focus picks",
                "Vow added effects",
                "Vow situational perks",
                "Combat styles",
                "Conditions",
                "Properties",
                "Focus pick budget",
                "Required content",
            ],
        )
        for link in links:
            with self.subTest(link=link.label):
                self.assertEqual(self.client.get(link.url).status_code, 200)

    def test_counts_read_the_rows(self) -> None:
        styles = next(link for link in self._links() if link.label == "Combat styles")
        self.assertEqual(styles.note, "1 style")

    def test_budget_row_opens_the_saved_config(self) -> None:
        config, _ = VowFocusPickConfig.objects.get_or_create(pk=1)
        config.budget_per_level = 6
        config.save()
        budget = next(link for link in self._links() if link.label == "Focus pick budget")
        self.assertEqual(budget.note, "6 points per level")
        self.assertEqual(
            budget.url, reverse("admin:arxii_vowfocuspickconfig_change", args=[config.pk])
        )

    def test_budget_row_before_the_config_exists_names_the_default(self) -> None:
        VowFocusPickConfig.objects.all().delete()
        budget = next(link for link in self._links() if link.label == "Focus pick budget")
        self.assertTrue(budget.note.endswith("points per level (default)"))
