"""Email delivery for invitation-gated account registration.

Reuses ``EmailServiceBase`` from ``world.roster.email_service`` rather than
adding a parallel sending helper: that base exists precisely so sibling
domain services can share ``_send_email`` without inheriting roster's
domain-specific signatures (see its docstring, #2162).

Until this module existed, ``issue_invite()`` created the row and stopped
there. The only delivery path was the Copy Link button on the staff invites
page, so every invitation had to be pasted into a staff member's own mail
client by hand, even though Resend is already wired up as the SMTP backend
for allauth's verification and password-reset mail.
"""

import logging

from django.conf import settings
from django.template import TemplateDoesNotExist, TemplateSyntaxError
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from world.registration.models import AccountInvite
from world.roster.email_service import EmailServiceBase

logger = logging.getLogger(__name__)

INVITE_SUBJECT = "You are invited to Arx II"


def build_invite_url(token: str) -> str:
    """Return the absolute signup URL that redeems ``token``.

    Mirrors the staff page's ``inviteLink()`` helper, which builds
    ``/register?invite=<token>`` against the browser's own origin. Server-side
    there is no request origin to lean on, so this uses ``SITE_URL`` -- the
    same setting every other outbound link in the roster email service uses.
    """
    return f"{settings.SITE_URL}/register?invite={token}"


class RegistrationEmailService(EmailServiceBase):
    """Outbound mail for account invitations."""

    @classmethod
    def send_account_invite(cls, invite: AccountInvite) -> bool:
        """Email the redemption link for ``invite`` to its bound address.

        Returns True when the send succeeded. Never raises: a mail failure
        must not undo an invite that was already created, and the staff page
        keeps Copy Link as a manual fallback for exactly that case.
        """
        context = {
            "invite_email": invite.email,
            "invite_url": build_invite_url(invite.token),
            "invited_by_name": invite.invited_by.username,
            "expires_at": invite.expires_at,
        }
        try:
            html_message = render_to_string("registration/email/account_invite.html", context)
        except (TemplateDoesNotExist, TemplateSyntaxError):
            # A broken template is a deploy fault, not an operational one, but
            # it must not take the invite down with it: the row is committed
            # and Copy Link still works. Log loudly and report failure.
            logger.exception("Invite email template failed to render for invite %s", invite.pk)
            return False
        return cls._send_email(
            subject=INVITE_SUBJECT,
            message=strip_tags(html_message),
            recipient_list=[invite.email],
            html_message=html_message,
        )
