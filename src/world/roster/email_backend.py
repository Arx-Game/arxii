"""Resend HTTPS API email backend.

Production blocks outbound SMTP (ports 587 and 465) at the hosting provider
level -- confirmed against both smtp.resend.com and smtp.gmail.com. Django's
SMTP backend against smtp.resend.com therefore times out, and that timeout
surfaces as an HTTP 500 on the signup endpoint (allauth sends a verification
email inline with account creation). Port 443 to api.resend.com is open and
verified working, so this backend sends mail over Resend's HTTPS API instead
of SMTP. See ADR-0216 for the full rationale and the rejected alternative
(asking the host to unblock SMTP).

Lives beside ``EmailServiceBase`` (``world.roster.email_service``): that class
is the low-level sender every domain email service in this codebase already
shares, and this backend is the transport layer underneath it (and underneath
allauth's own mail, which does not go through EmailServiceBase at all).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMultiAlternatives
import requests

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.core.mail.message import EmailMessage

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"

# A hung mail provider must never hang the request thread that triggered the
# send (that was exactly the SMTP failure mode this backend replaces), so the
# HTTP call always carries a short, explicit timeout.
RESEND_TIMEOUT_SECONDS = 10


class ResendAttachmentsNotSupportedError(Exception):
    """Raised when a message carries attachments this backend cannot send.

    The Resend HTTPS API does support a base64-encoded ``attachments`` field,
    but nothing in this codebase sends an attachment today -- every caller of
    ``EmailServiceBase._send_email`` (roster, registration, character_creation)
    sends body/html only, and allauth's own mail carries no attachments either.
    Rather than silently dropping a future attachment, this backend refuses
    loudly so the gap gets real support instead of a mail that quietly arrives
    without the file a user was told to expect.
    """


def _html_alternative(message: EmailMessage) -> str | None:
    """Return the text/html alternative body of ``message``, if any.

    ``EmailMultiAlternatives.attach_alternative(content, mimetype)`` appends to
    ``message.alternatives`` as a list of ``(content, mimetype)`` tuples. A
    plain ``EmailMessage`` has no such attribute at all.
    """
    if not isinstance(message, EmailMultiAlternatives):
        return None
    for content, mimetype in message.alternatives:
        if mimetype == "text/html":
            return str(content)
    return None


class ResendAPIEmailBackend(BaseEmailBackend):
    """Django email backend that sends via Resend's HTTPS API.

    Drop-in replacement for the SMTP backend: honours ``fail_silently`` the
    same way Django's built-in backends do (swallow and continue when True,
    raise on the first failure when False), and returns the count of messages
    actually sent, per the ``BaseEmailBackend.send_messages`` contract.
    """

    def send_messages(self, email_messages: Sequence[EmailMessage]) -> int:
        if not email_messages:
            return 0

        api_key = settings.RESEND_API_KEY
        sent_count = 0
        for message in email_messages:
            try:
                self._send_one(message, api_key)
            except (requests.exceptions.RequestException, ResendAttachmentsNotSupportedError):
                logger.exception(
                    "Resend API send failed for message %r",
                    message.subject,
                )
                if not self.fail_silently:
                    raise
            else:
                sent_count += 1
        return sent_count

    def _send_one(self, message: EmailMessage, api_key: str) -> None:
        if message.attachments:
            error_message = (
                f"Message {message.subject!r} has {len(message.attachments)} "
                "attachment(s); ResendAPIEmailBackend does not send attachments."
            )
            raise ResendAttachmentsNotSupportedError(error_message)

        payload: dict[str, object] = {
            "from": message.from_email,
            "to": list(message.to),
            "subject": message.subject,
            "text": message.body,
        }
        if message.cc:
            payload["cc"] = list(message.cc)
        if message.bcc:
            payload["bcc"] = list(message.bcc)
        if message.reply_to:
            payload["reply_to"] = list(message.reply_to)

        html_body = _html_alternative(message)
        if html_body:
            payload["html"] = html_body

        response = requests.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=RESEND_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
