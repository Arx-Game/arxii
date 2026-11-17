"""The staff admin for substances, Primum steps, the power curve and the Gift pick (#5125)."""

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from web.admin.tests.test_kindling_admin import form_data
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

    def test_substance_page_saves_related_and_opposed_from_both_sides(self) -> None:
        self.client.force_login(self.staff)
        url = reverse("admin:arxii_substance_change", args=[self.fire.pk])
        data = form_data(self.client.get(url))
        data["related_to"] = [str(self.light.pk)]
        data["opposed_to"] = [str(self.ice.pk)]
        data["_save"] = "Save"
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(
            relation_kinds_for(self.fire),
            {
                self.light.pk: SubstanceRelationKind.RELATED,
                self.ice.pk: SubstanceRelationKind.OPPOSED,
            },
        )
        # The pair is stored once, so the other page shows fire from its own side.
        other = self.client.get(reverse("admin:arxii_substance_change", args=[self.light.pk]))
        form = other.context["adminform"].form
        self.assertEqual(form.initial["related_to"], [self.fire.pk])
        self.assertEqual(list(form.initial["opposed_to"]), [])

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
