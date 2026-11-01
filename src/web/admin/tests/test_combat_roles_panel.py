"""The Combat roles panel on the admin front page (#4857, slice 1 of #4843).

Staff find every combat role authoring page from the front page; each link opens.
"""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from world.covenants.factories import CombatStyleFactory, CovenantRoleFactory
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
                "Vow pages",
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

    def test_the_vow_picker_lists_every_vow_and_opens_its_vow_page(self) -> None:
        role = CovenantRoleFactory(name="Fulmination")
        vows = next(link for link in self._links() if link.label == "Vow pages")
        self.assertEqual(vows.note, "1 vow")
        self.assertEqual(vows.picker.choices, [(role.pk, "Fulmination")])
        response = self.client.get(vows.picker.action, {"pk": role.pk})
        self.assertRedirects(response, reverse("admin_vow_builder", args=[role.pk]))
        self.assertContains(self.client.get(reverse("admin:index")), 'class="combat-roles-picker"')

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


class CombatRolesPanelPermissionTests(TestCase):
    """A staff account sees only the rows whose pages would open for it."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = get_user_model().objects.create_user(
            username="combat-roles-limited", password="x", is_staff=True
        )
        cls.staff.user_permissions.add(
            Permission.objects.get(codename="view_combatstyle"),
            Permission.objects.get(codename="change_conditiontemplate"),
        )

    def test_limited_staff_see_only_rows_they_can_open(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin:index"))
        self.assertEqual(resp.status_code, 200)
        links = resp.context["combat_roles_links"]
        self.assertEqual([link.label for link in links], ["Combat styles", "Conditions"])
        for link in links:
            with self.subTest(link=link.label):
                self.assertEqual(self.client.get(link.url).status_code, 200)


class CombatRolesPanelStylingTest(TestCase):
    """The panel's group and module rules reach the front page, not just its class names."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = get_user_model().objects.create_superuser(
            username="combat-roles-style", email="combat-roles-style@example.com", password="x"
        )

    def test_arx_admin_stylesheet_with_the_group_rules_is_linked(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin:index"))
        self.assertContains(resp, "admin/css/arx_admin.css")
        css = Path(finders.find("admin/css/arx_admin.css")).read_text()
        for selector in (".app-group-header", ".app-group-content"):
            with self.subTest(selector=selector):
                self.assertIn(selector, css)
