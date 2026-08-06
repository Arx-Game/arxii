"""Tests for the change-form "Export to content repo" button (#3018).

The button is a small ``{% block object-tools-items %}`` override in
``web/templates/admin/change_form.html`` (mirroring the pin button in
``change_list.html``'s override of the same block) that posts to
``admin_content_export_row`` with the row's ``<domain>.<model_name>`` label
and pk. It is gated three ways: the object must exist (a change form, not an
add form), the model must be corpus-owned (``content_export_tags
.content_exportable``), and the viewer must be a superuser.
"""

from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.magic.factories import EffectTypeFactory


class TestChangeFormExportButton(TestCase):
    """The button's presence/absence across model, permission, and add/change cases."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("staffer", "s@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.user_permissions.set(Permission.objects.all())
        cls.staff.save()

    def test_content_model_change_form_has_the_button_for_a_superuser(self) -> None:
        effect = EffectTypeFactory(name="Export Button Effect")
        self.client.force_login(self.super)

        resp = self.client.get(reverse("admin:arxii_effecttype_change", args=[effect.pk]))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Export to content repo")
        self.assertContains(resp, reverse("admin_content_export_row"))
        self.assertContains(resp, 'value="magic.effecttype"')
        self.assertContains(resp, f'value="{effect.pk}"')

    def test_non_content_model_change_form_has_no_button(self) -> None:
        group = Group.objects.create(name="Export Button Control Group")
        self.client.force_login(self.super)

        resp = self.client.get(reverse("admin:auth_group_change", args=[group.pk]))

        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Export to content repo")

    def test_non_superuser_staff_does_not_see_the_button(self) -> None:
        effect = EffectTypeFactory(name="Export Button Staff View Effect")
        self.client.force_login(self.staff)

        resp = self.client.get(reverse("admin:arxii_effecttype_change", args=[effect.pk]))

        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Export to content repo")

    def test_add_form_has_no_button(self) -> None:
        self.client.force_login(self.super)

        resp = self.client.get(reverse("admin:arxii_effecttype_add"))

        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Export to content repo")
