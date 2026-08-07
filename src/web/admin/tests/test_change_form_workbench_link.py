"""Tests for the change-form "Open in Authoring Workbench" link (#3020).

Same gating shape as the #3018 export button beside it: change form (not
add), credited model with prose fields, superuser only.
"""

from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.magic.factories import EffectTypeFactory


class TestChangeFormWorkbenchLink(TestCase):
    """Presence/absence of the workbench link across model, permission, and form cases."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("staffer", "s@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.user_permissions.set(Permission.objects.all())
        cls.staff.save()

    def test_credited_change_form_links_to_the_workbench_for_a_superuser(self) -> None:
        effect = EffectTypeFactory(name="Workbench Link Effect")
        self.client.force_login(self.super)

        resp = self.client.get(reverse("admin:arxii_effecttype_change", args=[effect.pk]))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Open in Authoring Workbench")
        self.assertContains(resp, reverse("admin_authoring_editor"))
        self.assertContains(resp, "model=magic.EffectType")

    def test_non_credited_change_form_has_no_link(self) -> None:
        group = Group.objects.create(name="Workbench Link Control Group")
        self.client.force_login(self.super)

        resp = self.client.get(reverse("admin:auth_group_change", args=[group.pk]))

        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Open in Authoring Workbench")

    def test_non_superuser_staff_does_not_see_the_link(self) -> None:
        effect = EffectTypeFactory(name="Workbench Link Staff Effect")
        self.client.force_login(self.staff)

        resp = self.client.get(reverse("admin:arxii_effecttype_change", args=[effect.pk]))

        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Open in Authoring Workbench")

    def test_add_form_has_no_link(self) -> None:
        self.client.force_login(self.super)

        resp = self.client.get(reverse("admin:arxii_effecttype_add"))

        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Open in Authoring Workbench")
