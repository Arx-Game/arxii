"""Unit tests for ``ArxAccountAdapter.is_open_for_signup`` (#3054).

Uses Django's ``RequestFactory`` with a raw JSON body to prove the adapter
can read the invite token/email off ``request.body`` the same way the real
headless signup view's request looks by the time ``post()`` runs (see the
seam explanation in ``evennia_extensions.adapters``). The end-to-end proof
against the real endpoint lives in ``test_signup_journey.py``.
"""

import json

from django.test import RequestFactory, TestCase

from evennia_extensions.adapters import ArxAccountAdapter
from evennia_extensions.factories import AccountFactory
from world.registration.factories import AccountInviteFactory
from world.registration.models import get_registration_config


def _json_post_request(payload: dict) -> object:
    return RequestFactory().post(
        "/api/auth/browser/v1/auth/signup",
        data=json.dumps(payload),
        content_type="application/json",
    )


class IsOpenForSignupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="adapter_test_staff", is_staff=True)

    def setUp(self):
        self.adapter = ArxAccountAdapter()

    def test_closed_with_no_invite_fields_rejected(self):
        request = _json_post_request({"username": "x", "email": "x@example.com", "password": "x"})
        self.assertFalse(self.adapter.is_open_for_signup(request))

    def test_closed_with_valid_invite_and_matching_email_allowed(self):
        invite = AccountInviteFactory(invited_by=self.staff, email="invitee@example.com")
        request = _json_post_request(
            {
                "username": "x",
                "email": "invitee@example.com",
                "password": "x",
                "invite_token": invite.token,
            }
        )
        self.assertTrue(self.adapter.is_open_for_signup(request))

    def test_closed_with_valid_invite_and_wrong_email_rejected(self):
        invite = AccountInviteFactory(invited_by=self.staff, email="invitee@example.com")
        request = _json_post_request(
            {
                "username": "x",
                "email": "someone-else@example.com",
                "password": "x",
                "invite_token": invite.token,
            }
        )
        self.assertFalse(self.adapter.is_open_for_signup(request))

    def test_open_registration_ignores_invite_state(self):
        config = get_registration_config()
        config.registration_open = True
        config.save(update_fields=["registration_open"])

        request = _json_post_request({"username": "x", "email": "x@example.com", "password": "x"})
        self.assertTrue(self.adapter.is_open_for_signup(request))

    def test_no_body_rejected_not_erroring(self):
        request = RequestFactory().post("/api/auth/browser/v1/auth/signup")
        self.assertFalse(self.adapter.is_open_for_signup(request))

    def test_reading_body_twice_is_safe(self):
        """Mirrors the real view: RESTView._parse_json reads request.body first."""
        invite = AccountInviteFactory(invited_by=self.staff, email="invitee@example.com")
        request = _json_post_request(
            {
                "username": "x",
                "email": "invitee@example.com",
                "password": "x",
                "invite_token": invite.token,
            }
        )
        first_read = request.body
        self.assertTrue(self.adapter.is_open_for_signup(request))
        self.assertEqual(first_read, request.body)


class NewUserTypeclassTests(TestCase):
    """Sentry ARX2-8: allauth's default ``new_user`` is ``get_user_model()()``.

    That is the base ``AccountDB``; Evennia pins ``db_typeclass_path`` to the
    class it was instantiated as, so every web-signup account stayed on ``AccountDB``
    forever and lacked the ``Account`` typeclass (no ``puppet``, no
    ``get_available_characters``, no ``cached_primary_persona_ids``).
    """

    def test_new_user_is_the_configured_account_typeclass(self):
        from django.conf import settings
        from evennia.utils.utils import class_from_module

        user = ArxAccountAdapter().new_user(_json_post_request({}))

        self.assertIsInstance(user, class_from_module(settings.BASE_ACCOUNT_TYPECLASS))
        self.assertEqual(user.db_typeclass_path, settings.BASE_ACCOUNT_TYPECLASS)
