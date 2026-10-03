"""The Majora threshold's minimum warp stage is a Soulfray stage (#4089)."""

from __future__ import annotations

from django.contrib import admin
from django.test import RequestFactory, TestCase
from evennia.accounts.models import AccountDB

from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.magic.admin import AudereMajoraThresholdForm
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.audere_majora import AudereMajoraThreshold


class WarpStagePickerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.admin_user = AccountDB.objects.create_superuser(
            "majoraadmin", "majoraadmin@example.com", "pw-123456"
        )
        soulfray = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME, has_progression=True)
        cls.sundering = ConditionStageFactory(condition=soulfray, stage_order=4, name="Sundering")
        cls.numb = ConditionStageFactory(
            condition=ConditionTemplateFactory(name="Poison test", has_progression=True),
            stage_order=1,
            name="Numb",
        )

    def test_the_form_refuses_a_stage_from_another_condition(self) -> None:
        form = AudereMajoraThresholdForm(data={"minimum_warp_stage": self.numb.pk})
        form.is_valid()
        self.assertIn("minimum_warp_stage", form.errors)
        self.assertIn("Soulfray", str(form.errors["minimum_warp_stage"]))

    def test_the_form_accepts_a_soulfray_stage(self) -> None:
        form = AudereMajoraThresholdForm(data={"minimum_warp_stage": self.sundering.pk})
        form.is_valid()
        self.assertNotIn("minimum_warp_stage", form.errors)

    def test_the_admin_field_offers_soulfray_stages_only(self) -> None:
        request = RequestFactory().get("/")
        request.user = self.admin_user
        model_admin = admin.site._registry[AudereMajoraThreshold]
        field = model_admin.get_form(request)().fields["minimum_warp_stage"]
        self.assertEqual(list(field.queryset), [self.sundering])

    def test_the_autocomplete_offers_soulfray_stages_only(self) -> None:
        self.client.force_login(self.admin_user)
        resp = self.client.get(
            "/admin/autocomplete/",
            {
                "app_label": "arxii",
                "model_name": "auderemajorathreshold",
                "field_name": "minimum_warp_stage",
                "term": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        ids = {int(result["id"]) for result in resp.json()["results"]}
        self.assertEqual(ids, {self.sundering.pk})

    def test_other_autocompletes_on_stages_are_unchanged(self) -> None:
        # ConditionCheckModifier has no registered standalone admin (it is an inline
        # only), so the autocomplete view would refuse that source entirely; use
        # ConditionStageOnEntryAdmin instead, the other registered admin whose
        # ``autocomplete_fields`` lists a ``ConditionStage`` FK (#4089 brief note).
        self.client.force_login(self.admin_user)
        resp = self.client.get(
            "/admin/autocomplete/",
            {
                "app_label": "arxii",
                "model_name": "conditionstageonentry",
                "field_name": "stage",
                "term": "",
            },
        )
        ids = {int(result["id"]) for result in resp.json()["results"]}
        self.assertTrue({self.sundering.pk, self.numb.pk} <= ids)
