"""Tests for the registry-wide credit-status filter/column injection (#3020).

Uses ``magic.EffectType`` as the sample credited model (registered admin,
factory, prose ``description`` field - same choice as
``test_change_form_export_button.py``) and ``auth.Group`` as the non-credited
control.
"""

from django.contrib import admin
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from web.admin.apps import _attach_credit_admin_extras
from web.admin.authoring.links import workbench_editor_url
from world.contributors.admin import CreditStatusListFilter, credit_status
from world.contributors.factories import ContentContributorFactory
from world.magic.factories import EffectTypeFactory
from world.magic.models import EffectType


class CreditAdminInjectionTests(TestCase):
    """The ready()-time pass attaches the filter and column exactly once."""

    def test_credited_admin_carries_filter_and_column(self) -> None:
        instance = admin.site._registry[EffectType]

        self.assertIn(CreditStatusListFilter, instance.list_filter)
        self.assertIn(credit_status, instance.list_display)

    def test_non_credited_admin_is_untouched(self) -> None:
        instance = admin.site._registry[Group]

        self.assertNotIn(CreditStatusListFilter, instance.list_filter)
        self.assertNotIn(credit_status, instance.list_display)

    def test_injection_pass_is_idempotent(self) -> None:
        _attach_credit_admin_extras()
        instance = admin.site._registry[EffectType]

        self.assertEqual(list(instance.list_filter).count(CreditStatusListFilter), 1)
        self.assertEqual(list(instance.list_display).count(credit_status), 1)


class CreditStatusChangelistTests(TestCase):
    """Filter partition and linked cell, proven through a real changelist GET."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")
        writer = ContentContributorFactory(name="Writer")
        reviewer = ContentContributorFactory(name="Reviewer")
        cls.unwritten = EffectTypeFactory(name="Credit Unwritten Effect")
        cls.written = EffectTypeFactory(name="Credit Written Effect", written_by=writer)
        cls.reviewed = EffectTypeFactory(
            name="Credit Reviewed Effect", written_by=writer, reviewed_by=reviewer
        )

    def _changelist(self, query: str = ""):
        self.client.force_login(self.super)
        return self.client.get(reverse("admin:arxii_effecttype_changelist") + query)

    def test_unwritten_lookup_shows_only_unwritten_rows(self) -> None:
        resp = self._changelist("?credit=unwritten")

        self.assertContains(resp, "Credit Unwritten Effect")
        self.assertNotContains(resp, "Credit Written Effect")
        self.assertNotContains(resp, "Credit Reviewed Effect")

    def test_written_lookup_means_written_and_not_reviewed(self) -> None:
        resp = self._changelist("?credit=written")

        self.assertContains(resp, "Credit Written Effect")
        self.assertNotContains(resp, "Credit Unwritten Effect")
        self.assertNotContains(resp, "Credit Reviewed Effect")

    def test_reviewed_lookup_shows_only_reviewed_rows(self) -> None:
        resp = self._changelist("?credit=reviewed")

        self.assertContains(resp, "Credit Reviewed Effect")
        self.assertNotContains(resp, "Credit Unwritten Effect")
        self.assertNotContains(resp, "Credit Written Effect")

    def test_cell_links_into_the_workbench_editor(self) -> None:
        resp = self._changelist()

        url = workbench_editor_url("magic.EffectType", self.unwritten.pk)
        self.assertContains(resp, url.replace("&", "&amp;"))
