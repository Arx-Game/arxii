"""The staff admin for substances, Primum steps, the power curve and the Gift pick (#5125)."""

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from web.admin.tests.support import form_data
from world.items.factories import ItemTemplateFactory
from world.magic.constants import GiftKind, SubstanceRelationKind
from world.magic.factories import GiftFactory, SubstanceFactory, SubstanceRelationFactory
from world.magic.models import PrimumStep, SubstancePowerStep, SubstanceRelation
from world.magic.services.resonance_environment import get_resonance_environment_config
from world.magic.services.substance_relations import (
    relation_kinds_for,
    set_substance_relations,
)


class SubstanceAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountDB.objects.create_superuser(
            "substance5125", "substance5125@example.com", "pw-123456"
        )
        cls.fire = SubstanceFactory(name="fire")
        cls.light = SubstanceFactory(name="light")
        cls.ice = SubstanceFactory(name="ice")

    def test_substance_page_saves_relationship_rows_and_harvest_item(self) -> None:
        """Rows of other substance and kind save once and show on both substances (F1, F2)."""
        coat_primum = ItemTemplateFactory(name="Fire Primum")
        self.client.force_login(self.staff)
        url = reverse("admin:arxii_substance_change", args=[self.fire.pk])
        page = self.client.get(url)
        self.assertContains(page, "Item created by harvesting")
        self.assertContains(page, "Each relationship is authored once and shows on both")
        self.assertContains(page, "admin/js/inlines.js")
        data = form_data(page)
        data.update(
            {
                "relations-TOTAL_FORMS": "3",
                "relations-INITIAL_FORMS": "0",
                "relations-0-other": str(self.light.pk),
                "relations-0-kind": SubstanceRelationKind.RELATED,
                "relations-1-other": str(self.ice.pk),
                "relations-1-kind": SubstanceRelationKind.OPPOSED,
                "harvest_item": str(coat_primum.pk),
                "_save": "Save",
            }
        )
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(
            relation_kinds_for(self.fire),
            {
                self.light.pk: SubstanceRelationKind.RELATED,
                self.ice.pk: SubstanceRelationKind.OPPOSED,
            },
        )
        coat_primum.refresh_from_db()
        self.assertEqual(coat_primum.primum_substance, self.fire)
        # The pair is stored once (fire first), so light's page draws fire as its own row,
        # and deleting that row there removes the pair for both.
        light_url = reverse("admin:arxii_substance_change", args=[self.light.pk])
        light_page = self.client.get(light_url)
        rows = light_page.context["adminform"].form.relations.initial
        self.assertEqual(rows, [{"other": self.fire.pk, "kind": SubstanceRelationKind.RELATED}])
        data = form_data(light_page)
        data.update(
            {
                "relations-TOTAL_FORMS": "1",
                "relations-INITIAL_FORMS": "1",
                "relations-0-other": str(self.fire.pk),
                "relations-0-kind": SubstanceRelationKind.RELATED,
                "relations-0-DELETE": "on",
                "_save": "Save",
            }
        )
        self.assertEqual(self.client.post(light_url, data).status_code, 302)
        self.assertEqual(
            relation_kinds_for(self.fire), {self.ice.pk: SubstanceRelationKind.OPPOSED}
        )

    def test_substance_page_refuses_a_harvest_item_another_substance_has(self) -> None:
        taken = ItemTemplateFactory(name="Ice Primum", primum_substance=self.ice)
        self.client.force_login(self.staff)
        url = reverse("admin:arxii_substance_change", args=[self.fire.pk])
        data = form_data(self.client.get(url))
        data.update(
            {
                "relations-TOTAL_FORMS": "1",
                "relations-INITIAL_FORMS": "0",
                "harvest_item": str(taken.pk),
                "_save": "Save",
            }
        )
        response = self.client.post(url, data)
        self.assertContains(response, "is already the harvest item of ice")
        taken.refresh_from_db()
        self.assertEqual(taken.primum_substance, self.ice)

    def test_gift_form_refuses_substance_on_minor_gift(self) -> None:
        gift = GiftFactory(kind=GiftKind.MAJOR, substance=self.fire)
        self.client.force_login(self.staff)
        url = reverse("admin:arxii_gift_change", args=[gift.pk])
        data = form_data(self.client.get(url))
        data["kind"] = GiftKind.MINOR
        data["substance"] = str(self.fire.pk)
        data["_save"] = "Save"
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A minor gift has no substance")

    def test_config_page_saves_a_step_row_and_a_curve_row(self) -> None:
        config = get_resonance_environment_config()
        self.client.force_login(self.staff)
        url = reverse("admin:arxii_resonanceenvironmentconfig_change", args=[config.pk])
        data = form_data(self.client.get(url))
        data["primumstep-0-rank"] = "1"
        data["primumstep-0-name"] = "Trace"
        data["primumstep-0-starts_at"] = "1"
        data["primumstep-0-points"] = "1"
        data["substancepowerstep-0-points_reached"] = "1"
        data["substancepowerstep-0-power"] = "1"
        data["_save"] = "Save"
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(PrimumStep.objects.get(rank=1).name, "Trace")
        self.assertEqual(SubstancePowerStep.objects.get(points_reached=1).power, 1)

    def test_relation_sync_refuses_a_substance_in_both_sets(self) -> None:
        SubstanceRelationFactory(
            substance_a=self.fire, substance_b=self.light, kind=SubstanceRelationKind.RELATED
        )
        with self.assertRaises(ValidationError):
            set_substance_relations(self.fire, related=[self.ice], opposed=[self.ice])
        # Nothing was written: the old row is still there.
        self.assertEqual(SubstanceRelation.objects.count(), 1)
