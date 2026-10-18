"""The StandoffConfig change form and its preview rail (#4415)."""

import re

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.standoffs.models import StandoffConfig

RAIL_CLASSES = (
    "standoff-config-cols",
    "standoff-config-main",
    "standoff-config-rail",
    "standoff-config-rail-note",
)


class StandoffConfigAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.author = AccountDB.objects.create_superuser(
            "cfgauthor", "cfgauthor@example.com", "pw-123456"
        )

    def setUp(self) -> None:
        self.config = StandoffConfig.load()
        self.url = reverse("admin:arxii_standoffconfig_change", args=[self.config.pk])
        self.client.force_login(self.author)

    def test_the_rail_previews_what_the_cause_numbers_do(self) -> None:
        self.config.hunger_margin_step = 15
        self.config.territory_patience = 4
        self.config.save(update_fields=["hunger_margin_step", "territory_patience"])
        response = self.client.get(self.url)
        self.assertContains(response, "after 3 unfed actions, by 45 percent.")
        self.assertContains(
            response, "A Territory group warns after action 3, fires after action 4."
        )
        self.assertContains(response, "Causes")

    def test_every_rail_class_has_a_rule_on_the_page(self) -> None:
        html = self.client.get(self.url).content.decode()
        styles = "".join(re.findall(r"<style>(.*?)</style>", html, flags=re.DOTALL))
        self.assertIn("admin/css/forms.css", html)
        for name in RAIL_CLASSES:
            self.assertRegex(html, rf'class="[^"]*\b{re.escape(name)}\b', name)
            self.assertRegex(styles, rf"\.{re.escape(name)}\s*\{{", name)

    def test_saving_writes_the_cause_numbers(self) -> None:
        form = self.client.get(self.url).context["adminform"].form
        data = {
            name: ("" if value is None else value)
            for name, value in form.initial.items()
            if name in form.fields
        }
        data.update({"hunger_margin_step": "20", "territory_patience": "5"})
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.hunger_margin_step, 20)
        self.assertEqual(self.config.territory_patience, 5)
