"""Journeys for techniques that shake enemy morale (#4619).

- Staff author a technique's morale effect inline on the Technique admin page, and the
  technique's effect summary then says it shakes morale.
- A morale row that removes no morale is refused on the page.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse

from integration_tests.harness import JourneyCase
from world.magic.factories import TechniqueFactory
from world.magic.models import Technique, TechniqueMoraleEffect


def _filled(bound_fields) -> dict[str, str | list[str]]:
    """What a browser posts for these bound fields untouched; unchecked boxes are left out."""
    data: dict[str, str | list[str]] = {}
    for bound in bound_fields:
        value = bound.value()
        if isinstance(value, bool):
            if value:
                data[bound.html_name] = "on"
        elif isinstance(value, (list, tuple)):
            data[bound.html_name] = [str(item) for item in value]
        else:
            data[bound.html_name] = "" if value is None else str(value)
    return data


class AuthoringAMoraleEffect(JourneyCase):
    """Staff set a technique's morale effect on its own admin page."""

    def setUp(self) -> None:
        super().setUp()
        staff = get_user_model().objects.create_user(
            username="warden", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)
        self.technique = TechniqueFactory(damage_profile=False)
        self.url = reverse("admin:arxii_technique_change", args=[self.technique.pk])

    def change_post(self, row: dict[str, object]) -> dict[str, str | list[str]]:
        """The change form's post with the morale inline filled in from *row*."""
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "morale_effect-TOTAL_FORMS")
        data = _filled(page.context["adminform"].form)
        for inline in page.context["inline_admin_formsets"]:
            formset = inline.formset
            data.update(_filled(formset.management_form))
            for form in formset.forms:
                data.update(_filled(form))
            if formset.prefix == "morale_effect":
                for name, value in row.items():
                    data[f"morale_effect-0-{name}"] = str(value)
        return data

    def test_staff_add_a_morale_effect_on_the_technique_page(self) -> None:
        data = self.change_post({"base_morale": 30, "morale_per_extra_sl": 10})

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 302)
        row = TechniqueMoraleEffect.objects.get(technique=self.technique)
        self.assertEqual(
            (row.base_morale, row.morale_per_extra_sl, row.minimum_success_level), (30, 10, 1)
        )
        refreshed = Technique.objects.get(pk=self.technique.pk)
        self.assertIn("Shakes morale.", refreshed.cached_effect_summary["summary"])

    def test_a_row_that_removes_no_morale_is_refused_on_the_page(self) -> None:
        data = self.change_post(
            {
                "minimum_success_level": 2,
                "base_morale": 0,
                "morale_intensity_multiplier": 0,
                "morale_per_extra_sl": 0,
            }
        )

        response = self.client.post(self.url, data)

        self.assertContains(response, "This row removes no morale.")
        self.assertFalse(TechniqueMoraleEffect.objects.filter(technique=self.technique).exists())
