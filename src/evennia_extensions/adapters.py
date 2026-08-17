"""Custom django-allauth adapters for Arx II."""

import json
import logging

from allauth.account.adapter import DefaultAccountAdapter

from evennia_extensions.models import PlayerData
from world.registration import services as registration_services
from world.registration.models import get_registration_config

logger = logging.getLogger(__name__)


class ArxAccountAdapter(DefaultAccountAdapter):
    """Custom account adapter for Arx II that creates PlayerData on signup."""

    def send_mail(self, template_prefix, email, context):
        """Account mail is best-effort: a failed send never fails the request (#3193).

        On 2026-08-16 an SMTP timeout inside the signup verification send
        propagated out of ``/api/auth/browser/v1/auth/signup`` as an HTML 500,
        after the account row and invite redemption had already committed — the
        user got a real account and an apparent failure, and the retry read as
        "username taken". The same send also runs at login
        (``send_verification_email_at_login``), where a mail outage blocked
        existing users from signing in. So every allauth account send
        (verification, password reset) is caught here: the failure is logged
        and recorded staff-visibly via ``record_mail_failure``, and the request
        completes. Staff can hand over a verification link directly (the
        ``/api/staff/verification-link/`` surface), and the next login retries
        the send anyway.
        """
        try:
            super().send_mail(template_prefix, email, context)
        except Exception as exc:
            logger.exception("Account mail send failed (%s to %s)", template_prefix, email)
            registration_services.record_mail_failure(email, template_prefix, exc)

    def is_open_for_signup(self, request):
        """Registration is closed by default; a valid per-email invite opens it (#3054).

        Seam decision: the headless signup endpoint
        (``allauth.headless.account.views.SignupView.post``) calls this hook
        AFTER ``RESTView.handle()`` has already JSON-decoded the POST body
        into ``self.data`` (to build/validate ``SignupInput``) but BEFORE
        ``post()`` does anything else — so the validated ``SignupInput`` is
        not passed to this hook, only ``request``. Django's
        ``HttpRequest.body`` is a cached property (read once, stashed on
        ``request._body``); ``RESTView._parse_json`` already triggered that
        cache by decoding it, so re-parsing it here is a free re-read of the
        same bytes, not a second consumption of the request stream. Proven
        against the real endpoint by the journey tests in
        ``world/registration/tests/test_signup_journey.py``.

        Returns a bare bool — never distinguishes *why* signup is refused
        (no invite / wrong email / expired / revoked), so allauth's
        ``ForbiddenResponse`` is the same neutral rejection for every
        invite-failure mode (leak-analysis: no oracle for probing which
        emails hold invites).
        """
        if get_registration_config().registration_open:
            return True
        email, token = self._invite_fields_from_request(request)
        return registration_services.signup_allowed(email, token)

    @staticmethod
    def _invite_fields_from_request(request) -> tuple[str, str]:
        """Best-effort read of ``email``/``invite_token`` from the raw JSON POST body."""
        body = request.body
        if not body:
            return "", ""
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return "", ""
        if not isinstance(data, dict):
            return "", ""
        return str(data.get("email") or ""), str(data.get("invite_token") or "")

    def save_user(self, request, user, form, commit=True):
        """Save user, create associated PlayerData, and stamp invite redemption."""
        # Call parent method to save the user
        user = super().save_user(request, user, form, commit)

        if commit:
            # Create PlayerData for the new user
            PlayerData.objects.get_or_create(account=user)

            email, token = self._invite_fields_from_request(request)
            if token:
                registration_services.redeem_invite(token, email, user)

        return user
