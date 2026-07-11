"""Email notifications for character-generation application review (#2162).

Reuses EmailServiceBase's send/staff-list helpers by inheritance —
character_creation already depends on roster (finalization creates tenures),
and the alternative (a generic notification app) was rejected in the spec.
CGEmailService extends EmailServiceBase rather than RosterEmailService itself:
RosterEmailService's send_application_approved/send_application_denied take a
different domain signature (a `tenure` arg CG doesn't have), so subclassing it
directly and overriding those names with a narrower signature would violate
the Liskov Substitution Principle (ty: invalid-method-override).
Plain-text bodies; no HTML templates needed at this size.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.roster.email_service import EmailServiceBase

if TYPE_CHECKING:
    from world.character_creation.models import DraftApplication

logger = logging.getLogger(__name__)


class CGEmailService(EmailServiceBase):
    """Notifications for the CG DraftApplication review loop."""

    @classmethod
    def _applicant_email(cls, application: DraftApplication) -> str | None:
        """The applicant's email, from the survives-draft-deletion FK on the application."""
        account = application.player_account
        if not account:
            return None
        return account.email or None

    @classmethod
    def _character_name(cls, application: DraftApplication) -> str:
        """The character's name.

        `DraftApplication.character_name` is only populated at approval time, so
        before that (submission, revisions, denial) fall back to the draft's
        staged first name while the draft still exists.
        """
        if application.character_name:
            return application.character_name
        if application.draft is not None:
            name = application.draft.draft_data.get("first_name", "")
            if name:
                return name
        return "your character"

    @classmethod
    def handle_submission(cls, application: DraftApplication) -> bool:
        """Confirmation to the applicant + notification to staff."""
        ok = True
        email = cls._applicant_email(application)
        character_name = cls._character_name(application)
        if email:
            ok = cls._send_email(
                subject=f"Application submitted: {character_name}",
                message=(
                    f"Your character application for {character_name} has been "
                    "submitted for staff review. You'll get another email when "
                    "it's reviewed. Check status any time at "
                    "/characters/create/application."
                ),
                recipient_list=[email],
            )
        staff = cls._get_staff_emails()
        if staff:
            ok = (
                cls._send_email(
                    subject=f"New character application: {character_name}",
                    message="A new character application is awaiting review.",
                    recipient_list=staff,
                )
                and ok
            )
        return ok

    @classmethod
    def send_application_approved(cls, application: DraftApplication) -> bool:
        email = cls._applicant_email(application)
        if not email:
            return False
        character_name = cls._character_name(application)
        return cls._send_email(
            subject=f"Application approved: {character_name}",
            message=(
                f"{character_name} has been approved! Log in and enter the game to start playing."
            ),
            recipient_list=[email],
        )

    @classmethod
    def send_application_denied(cls, application: DraftApplication) -> bool:
        email = cls._applicant_email(application)
        if not email:
            return False
        character_name = cls._character_name(application)
        return cls._send_email(
            subject=f"Application denied: {character_name}",
            message=(
                f"Your application for {character_name} was not approved. "
                "See the reviewer comments on your application page."
            ),
            recipient_list=[email],
        )

    @classmethod
    def send_revisions_requested(cls, application: DraftApplication) -> bool:
        email = cls._applicant_email(application)
        if not email:
            return False
        character_name = cls._character_name(application)
        return cls._send_email(
            subject=f"Revisions requested: {character_name}",
            message=(
                f"A reviewer requested revisions to your application for "
                f"{character_name}. See their comments and resubmit at "
                "/characters/create/application."
            ),
            recipient_list=[email],
        )
