"""The admin never bypasses 2FA and never shows a TOTP secret (#3591, decisions 11-12)."""

from allauth.mfa.models import Authenticator
from django.contrib import admin
from django.test import TestCase
from django.urls import reverse

from evennia_extensions.factories import AccountFactory
from evennia_extensions.mfa_adapter import ArxMFAAdapter

PASSWORD = "AdminPass123!"  # noqa: S105 - test fixture value, not a real credential


class AdminLoginRoutesThroughTheSiteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="admin_2fa_staff", is_staff=True, is_superuser=True)
        cls.staff.set_password(PASSWORD)
        cls.staff.save()
        Authenticator.objects.create(
            user=cls.staff,
            type=Authenticator.Type.TOTP,
            data={"secret": ArxMFAAdapter().encrypt("JBSWY3DPEHPK3PXP")},
        )

    def test_anonymous_admin_visit_redirects_to_the_site_login(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/login?next=/admin/")

    def test_password_only_post_to_admin_login_does_not_sign_in(self):
        response = self.client.post(
            "/admin/login/", {"username": "admin_2fa_staff", "password": PASSWORD}
        )
        self.assertNotEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_signed_in_staff_reach_the_admin(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/admin/").status_code, 200)


class AuthenticatorAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="admin_2fa_viewer", is_staff=True, is_superuser=True)
        cls.player = AccountFactory(username="admin_2fa_player")
        cls.row = Authenticator.objects.create(
            user=cls.player,
            type=Authenticator.Type.TOTP,
            data={"secret": ArxMFAAdapter().encrypt("JBSWY3DPEHPK3PXP")},
        )

    def test_change_form_has_no_data_field(self):
        self.client.force_login(self.staff)
        url = reverse("admin:mfa_authenticator_change", args=[self.row.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="data"')
        self.assertNotContains(response, "JBSWY3DPEHPK3PXP")

    def test_no_add_permission(self):
        model_admin = admin.site._registry[Authenticator]
        self.assertFalse(model_admin.has_add_permission(None))
