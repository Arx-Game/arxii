"""The combat style's admin page (#4884): every new field, and the gear kinds inline.

Expected text comes from the approved demo's admin card ("Change combat style").
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from world.covenants.factories import CombatStyleFactory, CombatStyleGearFactory
from world.items.constants import GearArchetype

GEAR_HELP = (
    "One row per kind. Weapon kinds make the attack profile, armor kinds the defense "
    "profile; using any other kind turns the bonus off."
)


class CombatStyleAdminPageTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = get_user_model().objects.create_superuser(
            username="style-admin-staff", email="style-admin@example.com", password="x"
        )
        cls.style = CombatStyleFactory(name="The Daring Dance")
        CombatStyleGearFactory(style=cls.style, gear_archetype=GearArchetype.MELEE_ONE_HAND)

    def setUp(self) -> None:
        self.client.force_login(self.staff)

    def page(self) -> str:
        resp = self.client.get(reverse("admin:arxii_combatstyle_change", args=[self.style.pk]))
        self.assertEqual(resp.status_code, 200)
        return " ".join(resp.content.decode().split())

    def test_the_page_edits_every_field_of_the_style(self) -> None:
        html = self.page()
        for field in ("skill", "hit_stat", "taught_by", "compatible_roles"):
            self.assertIn(f'name="{field}"', html, field)
        self.assertIn("Works with vows", html)

    def test_the_gear_kinds_inline_shows_its_help_line_on_the_page(self) -> None:
        html = self.page()
        self.assertIn("Gear kinds", html)
        self.assertIn(GEAR_HELP, html)

    def test_gear_kinds_offer_weapons_and_armor_only(self) -> None:
        html = self.page()
        self.assertIn('value="melee_one_hand"', html)
        self.assertIn('value="heavy_armor"', html)
        for kind in ("jewelry", "clothing", "other"):
            self.assertNotIn(f'<option value="{kind}"', html, kind)
