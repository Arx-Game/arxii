"""Root-cause reproduction attempt for issue #3195.

The issue's leading, unproven hypothesis is that Django's auth layer is how a
bare (non-typeclassed) AccountDB enters the idmapper cache: AUTH_USER_MODEL is
AccountDB, and every authenticated web request loads a user via
django.contrib.auth.get_user(), which resolves through
ModelBackend.get_user() -> UserModel._default_manager.get(pk=...).

This test drives a real authenticated admin request (force_login, then a GET
that touches request.user) and inspects AccountDB.get_all_cached_instances()
afterwards for an instance whose exact __class__ is the bare AccountDB model
rather than a subclassing typeclass.
"""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.factories import AccountFactory


class AuthLayerBareAccountReproductionTests(TestCase):
    """Does an authenticated request leave a bare AccountDB in the idmapper cache."""

    def test_authenticated_admin_request_does_not_leave_bare_accountdb_cached(self) -> None:
        account = AccountFactory(is_staff=True)
        account.is_superuser = True
        account.save()

        logged_in = self.client.force_login(account)
        self.assertIsNone(logged_in)  # force_login returns None on success

        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)

        bare_instances = [
            obj
            for obj in AccountDB.get_all_cached_instances()
            if type(obj) is AccountDB  # exact-class check is the point
        ]

        self.assertEqual(
            bare_instances,
            [],
            "Reproduced #3195: an authenticated admin request left a bare "
            f"AccountDB in the idmapper cache: pk(s) {[o.pk for o in bare_instances]}.",
        )
