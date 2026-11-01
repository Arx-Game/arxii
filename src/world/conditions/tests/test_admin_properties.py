"""A condition's properties are editable in the admin, popup included (#4857, slice 1 of #4843).

Perk situations and prerequisites match a condition by the properties it carries
(``world.covenants.perks.evaluators._carries_property_q``), so the condition form,
and the "+" popup that technique, vow-effect and standoff forms open, must offer them.
"""

from django.contrib.admin.widgets import AutocompleteSelectMultiple
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from world.conditions.admin import PROPERTIES_HELP
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.conditions.models import ConditionStage
from world.mechanics.factories import PropertyFactory


class ConditionPropertiesAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = get_user_model().objects.create_superuser(
            username="cond-props-staff", email="cond-props@example.com", password="x"
        )
        cls.prop = PropertyFactory(name="indulgence-4857")
        cls.template = ConditionTemplateFactory(name="Craving 4857")
        cls.template.properties.add(cls.prop)
        cls.stage = ConditionStageFactory(condition=cls.template, stage_order=1)

    def setUp(self) -> None:
        self.client.force_login(self.staff)

    def test_popup_add_form_offers_properties(self) -> None:
        url = reverse("admin:arxii_conditiontemplate_add") + "?_to_field=id&_popup=1"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        field = resp.context["adminform"].form.fields["properties"]
        self.assertEqual(field.help_text, PROPERTIES_HELP)

    def test_change_form_shows_the_property_a_condition_carries(self) -> None:
        resp = self.client.get(
            reverse("admin:arxii_conditiontemplate_change", args=[self.template.pk])
        )
        self.assertEqual(resp.status_code, 200)
        form = resp.context["adminform"].form
        self.assertIn("properties", form.fields)
        self.assertEqual(list(form.initial["properties"]), [self.prop])

    def test_stage_form_offers_properties_as_a_searchable_picker(self) -> None:
        resp = self.client.get(reverse("admin:arxii_conditionstage_change", args=[self.stage.pk]))
        self.assertEqual(resp.status_code, 200)
        field = resp.context["adminform"].form.fields["properties"]
        self.assertIsInstance(field.widget.widget, AutocompleteSelectMultiple)

    def test_stage_inline_on_the_condition_page_offers_properties(self) -> None:
        resp = self.client.get(
            reverse("admin:arxii_conditiontemplate_change", args=[self.template.pk])
        )
        stage_formsets = [
            inline.formset
            for inline in resp.context["inline_admin_formsets"]
            if inline.formset.model is ConditionStage
        ]
        self.assertEqual(len(stage_formsets), 1)
        field = stage_formsets[0].forms[0].fields["properties"]
        self.assertIsInstance(field.widget.widget, AutocompleteSelectMultiple)

    def test_stage_properties_picker_search_finds_the_property(self) -> None:
        resp = self.client.get(
            reverse("admin:autocomplete"),
            {
                "app_label": "arxii",
                "model_name": "conditionstage",
                "field_name": "properties",
                "term": "indulgence",
            },
        )
        self.assertEqual(resp.status_code, 200)
        names = [row["text"] for row in resp.json()["results"]]
        self.assertIn(str(self.prop), names)
