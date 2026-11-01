"""The Combat roles panel on the admin front page (#4857, slice 1 of #4843).

Staff find every combat role authoring page from the front page; each link opens.
"""

from pathlib import Path
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from world.conditions.factories import ConditionTemplateFactory
from world.covenants.factories import (
    CombatStyleFactory,
    CovenantRoleFactory,
    VowFocusPickFactory,
)
from world.covenants.models import VowFocusPickConfig
from world.mechanics.factories import PropertyFactory


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
                "Combo map",
                "Focus pick budget",
                "Missing combat content",
            ],
        )
        for link in links:
            with self.subTest(link=link.label):
                if link.url:
                    self.assertEqual(self.client.get(link.url).status_code, 200)
                else:
                    self.assertTrue(link.pickers, "a row with no page of its own needs a picker")

    def test_the_missing_combat_content_row_counts_the_open_flags(self) -> None:
        def shown() -> tuple[int, str]:
            row = next(link for link in self._links() if link.label == "Missing combat content")
            self.assertEqual(row.url, reverse("admin_combat_content"))
            return row.flag_count, row.note

        self.assertEqual(shown(), (0, "no open flags"))
        CovenantRoleFactory(name="Warden")
        self.assertEqual(shown(), (1, "open flag"))
        VowFocusPickFactory(covenant_role=CovenantRoleFactory(name="Aegis"), name="Bare")
        # Aegis now has a pick, but that pick has no payload; Warden still has none.
        self.assertEqual(shown(), (2, "open flags"))
        body = self.client.get(reverse("admin:index")).content.decode()
        self.assertIn('<span class="combat-roles-flagdot">2</span> open flags', body)

    def test_the_vow_picker_lists_every_vow_and_opens_its_vow_page(self) -> None:
        role = CovenantRoleFactory(name="Fulmination")
        vows = next(link for link in self._links() if link.label == "Vow pages")
        self.assertEqual(vows.note, "1 vow")
        (picker,) = vows.pickers
        self.assertEqual(picker.choices, [(role.pk, "Fulmination")])
        response = self.client.get(picker.action, {"pk": role.pk})
        self.assertRedirects(response, reverse("admin_vow_builder", args=[role.pk]))
        self.assertContains(self.client.get(reverse("admin:index")), 'class="combat-roles-picker"')

    def test_the_combo_map_row_opens_a_property_or_a_condition(self) -> None:
        prop = PropertyFactory(name="Indulgence")
        condition = ConditionTemplateFactory(name="Tipsy")
        combo = next(link for link in self._links() if link.label == "Combo map")
        by_label = {picker.label: picker for picker in combo.pickers}
        self.assertEqual(list(by_label), ["property", "condition"])
        self.assertIn((prop.pk, "Indulgence"), by_label["property"].choices)
        self.assertIn((condition.pk, "Tipsy"), by_label["condition"].choices)
        response = self.client.get(by_label["property"].action, {"pk": prop.pk})
        self.assertRedirects(response, reverse("admin_combo_map_property", args=[prop.pk]))
        response = self.client.get(by_label["condition"].action, {"pk": condition.pk})
        self.assertRedirects(response, reverse("admin_combo_map_condition", args=[condition.pk]))
        body = self.client.get(reverse("admin:index")).content.decode()
        # Each select is named by visible text: the row's label and its own button.
        row = re.search(r'id="(combat-roles-link-\d+)">Combo map</th>', body).group(1)
        self.assertIn(f'aria-labelledby="{row} combat-roles-open-', body)
        self.assertRegex(body, r'id="combat-roles-open-\d+-2">Open condition</button>')

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
        self.assertEqual(
            [link.label for link in links], ["Combat styles", "Conditions", "Combo map"]
        )
        combo = links[-1]
        self.assertEqual([picker.label for picker in combo.pickers], ["condition"])
        for link in links[:-1]:
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
