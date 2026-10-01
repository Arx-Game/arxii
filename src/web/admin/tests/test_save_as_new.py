"""Every first-party change form offers "Save as new" (#4094).

Through the admin's HTTP views as a superuser: the button is on an ``arxii``
change page, posting it creates a second row with the rest copied, an admin that
refuses adds does not offer it, and Evennia's own admins keep their defaults.
"""

from django.contrib import admin
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.game_clock.models import ScheduledTaskRecord
from world.societies.factories import OrganizationTypeFactory
from world.societies.models import OrganizationType


class SaveAsNewTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.root = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-1")
        cls.org_type = OrganizationTypeFactory(name="Noble family", rank_1_title="Patriarch")

    def setUp(self) -> None:
        self.client.force_login(self.root)

    def test_every_first_party_admin_has_save_as_on(self) -> None:
        first_party = [m for m in admin.site._registry if m._meta.app_label == "arxii"]
        self.assertTrue(first_party)
        off = [m.__name__ for m in first_party if not admin.site._registry[m].save_as]
        self.assertEqual(off, [])
        # A third-party admin keeps Django's default.
        self.assertFalse(admin.site._registry[Group].save_as)

    def test_change_form_offers_save_as_new_in_place_of_save_and_add_another(self) -> None:
        url = reverse("admin:arxii_organizationtype_change", args=(self.org_type.pk,))
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="_saveasnew"')
        self.assertNotContains(resp, 'name="_addanother"')

    def test_save_as_new_creates_a_second_row_with_the_rest_copied(self) -> None:
        url = reverse("admin:arxii_organizationtype_change", args=(self.org_type.pk,))
        page = self.client.get(url)
        form = page.context["adminform"].form
        data = {}
        for name in form.fields:
            value = form[name].value()
            if value is not None:
                data[name] = value
        for formset in (f.formset for f in page.context["inline_admin_formsets"]):
            for key, value in formset.management_form.initial.items():
                data[f"{formset.prefix}-{key}"] = value
        data["name"] = "Merchant family"
        data["_saveasnew"] = "Save as new"
        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 302, resp.content[:300])
        self.assertEqual(OrganizationType.objects.count(), 2)
        copy = OrganizationType.objects.get(name="Merchant family")
        self.assertNotEqual(copy.pk, self.org_type.pk)
        self.assertEqual(copy.rank_1_title, "Patriarch")

    def test_an_admin_that_refuses_adds_shows_no_button(self) -> None:
        record = ScheduledTaskRecord.objects.create(task_key="nightly-sweep")
        self.assertTrue(admin.site._registry[ScheduledTaskRecord].save_as)
        resp = self.client.get(reverse("admin:arxii_scheduledtaskrecord_change", args=(record.pk,)))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'name="_saveasnew"')
