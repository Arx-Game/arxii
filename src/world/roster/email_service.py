"""
Email service for roster application notifications.
Handles sending approval/rejection emails and password resets.
"""

import logging
from typing import TYPE_CHECKING, Optional

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.html import strip_tags
from django.utils.http import urlsafe_base64_encode

from world.roster.models import RosterApplication, RosterTenure

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

logger = logging.getLogger(__name__)


class RosterEmailService:
    """Service for sending roster-related emails."""

    @classmethod
    def send_application_confirmation(cls, application: RosterApplication) -> bool:
        """
        Send confirmation email when a player submits an application.

        Args:
            application: The RosterApplication that was submitted

        Returns:
            bool: True if email was sent successfully
        """
        try:
            subject = (
                f"[Arx II] Application Received for {application.character.db_key}"
            )

            context = {
                "character_name": application.character.db_key,
                "application_text": application.application_text,
                "player_name": application.player_data.account.username,
                "application_id": application.id,
                "application_date": application.applied_date,
            }

            html_message = render_to_string(
                "roster/email/application_confirmation.html", context
            )
            plain_message = strip_tags(html_message)

            return cls._send_email(
                subject=subject,
                message=plain_message,
                html_message=html_message,
                recipient_list=[application.player_data.account.email],
            )

        except Exception as e:
            logger.error(
                f"Failed to send application confirmation for app {application.id}: {e}"
            )
            return False

    @classmethod
    def send_application_approved(
        cls, application: RosterApplication, tenure: RosterTenure
    ) -> bool:
        """
        Send approval email when an application is approved.

        Args:
            application: The approved RosterApplication
            tenure: The newly created RosterTenure

        Returns:
            bool: True if email was sent successfully
        """
        try:
            subject = (
                f"[Arx II] Application Approved for {application.character.db_key}"
            )

            context = {
                "character_name": application.character.db_key,
                "player_name": application.player_data.account.username,
                "tenure_display": tenure.display_name,
                "approved_by": (
                    application.reviewed_by.account.username
                    if application.reviewed_by
                    else "Staff"
                ),
                "approved_date": application.reviewed_date,
                "review_notes": application.review_notes,
                "login_url": "https://arxmush.org/",  # TODO: Make configurable
            }

            html_message = render_to_string(
                "roster/email/application_approved.html", context
            )
            plain_message = strip_tags(html_message)

            return cls._send_email(
                subject=subject,
                message=plain_message,
                html_message=html_message,
                recipient_list=[application.player_data.account.email],
            )

        except Exception as e:
            logger.error(f"Failed to send approval email for app {application.id}: {e}")
            return False

    @classmethod
    def send_application_denied(cls, application: RosterApplication) -> bool:
        """
        Send denial email when an application is rejected.

        Args:
            application: The denied RosterApplication

        Returns:
            bool: True if email was sent successfully
        """
        try:
            subject = f"[Arx II] Application Update for {application.character.db_key}"

            context = {
                "character_name": application.character.db_key,
                "player_name": application.player_data.account.username,
                "reviewed_by": (
                    application.reviewed_by.account.username
                    if application.reviewed_by
                    else "Staff"
                ),
                "reviewed_date": application.reviewed_date,
                "review_notes": application.review_notes,
                "roster_url": "https://arxmush.org/roster/",  # TODO: Make configurable
            }

            html_message = render_to_string(
                "roster/email/application_denied.html", context
            )
            plain_message = strip_tags(html_message)

            return cls._send_email(
                subject=subject,
                message=plain_message,
                html_message=html_message,
                recipient_list=[application.player_data.account.email],
            )

        except Exception as e:
            logger.error(f"Failed to send denial email for app {application.id}: {e}")
            return False

    @classmethod
    def send_staff_application_notification(
        cls, application: RosterApplication
    ) -> bool:
        """
        Send notification to staff when a new application is submitted.

        Args:
            application: The new RosterApplication

        Returns:
            bool: True if email was sent successfully
        """
        try:
            subject = f"[Arx II Staff] New Application: {application.character.db_key}"

            policy_info = application.get_policy_review_info()

            context = {
                "character_name": application.character.db_key,
                "character_pk": application.character.pk,
                "player_name": application.player_data.account.username,
                "application_text": application.application_text,
                "application_id": application.id,
                "application_date": application.applied_date,
                "policy_info": policy_info,
                "review_url": (
                    f"https://arxmush.org/admin/roster/rosterapplication/"
                    f"{application.id}/"
                ),  # TODO: Make configurable
            }

            html_message = render_to_string(
                "roster/email/staff_notification.html", context
            )
            plain_message = strip_tags(html_message)

            # Get staff email list (could be configurable)
            staff_emails = cls._get_staff_emails()

            if staff_emails:
                return cls._send_email(
                    subject=subject,
                    message=plain_message,
                    html_message=html_message,
                    recipient_list=staff_emails,
                )

            return True  # No staff to notify is not an error

        except Exception as e:
            logger.error(
                f"Failed to send staff notification for app {application.id}: {e}"
            )
            return False

    @classmethod
    def send_password_reset_email(
        cls, user: AbstractUser, domain: str | None = None
    ) -> bool:
        """
        Send password reset email using Django's built-in token system.

        Args:
            user: The User account to send reset email to
            domain: Domain for the reset URL (optional)

        Returns:
            bool: True if email was sent successfully
        """
        try:
            if not domain:
                domain = getattr(settings, "SITE_DOMAIN", "arxmush.org")

            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))

            subject = "[Arx II] Password Reset Request"

            context = {
                "user": user,
                "domain": domain,
                "uid": uid,
                "token": token,
                "protocol": "https",
                "reset_url": f"https://{domain}/account/password/reset/key/{uid}-{token}/",
            }

            html_message = render_to_string("roster/email/password_reset.html", context)
            plain_message = strip_tags(html_message)

            return cls._send_email(
                subject=subject,
                message=plain_message,
                html_message=html_message,
                recipient_list=[user.email],
            )

        except Exception as e:
            logger.error(f"Failed to send password reset email to {user.email}: {e}")
            return False

    @classmethod
    def _send_email(
        cls,
        subject: str,
        message: str,
        recipient_list: list,
        html_message: Optional[str] = None,
        from_email: Optional[str] = None,
    ) -> bool:
        """
        Internal method to send emails via Django's email system.

        Args:
            subject: Email subject
            message: Plain text message
            recipient_list: List of recipient email addresses
            html_message: Optional HTML version of the message
            from_email: Optional from email (uses DEFAULT_FROM_EMAIL if not provided)

        Returns:
            bool: True if email was sent successfully
        """
        try:
            if not from_email:
                from_email = getattr(
                    settings, "DEFAULT_FROM_EMAIL", "noreply@arxmush.org"
                )

            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=recipient_list,
                html_message=html_message,
                fail_silently=False,
            )

            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    @classmethod
    def _get_staff_emails(cls) -> list:
        """
        Get list of staff email addresses for notifications.

        Returns:
            list: List of staff email addresses
        """
        # TODO: This could be made configurable or pulled from a staff group
        staff_emails = getattr(settings, "STAFF_NOTIFICATION_EMAILS", [])

        if not staff_emails:
            # Fallback to admin emails
            admin_emails = [admin[1] for admin in getattr(settings, "ADMINS", [])]
            return admin_emails

        return staff_emails

    @classmethod
    def handle_new_application(cls, application: RosterApplication) -> bool:
        """
        Handle all email notifications for a newly created application.
        This replaces the previous signal-based approach with explicit calls.

        Args:
            application: The newly created RosterApplication

        Returns:
            bool: True if all emails were sent successfully
        """
        success = True

        # Send confirmation email to player
        try:
            if not cls.send_application_confirmation(application):
                success = False
                logger.error(
                    f"Failed confirmation email for application {application.id}"
                )
            else:
                logger.info(f"Sent confirmation email for application {application.id}")
        except Exception as e:
            success = False
            logger.error(
                f"Exception sending confirmation email for application {application.id}: {e}"
            )

        # Send notification email to staff
        try:
            if not cls.send_staff_application_notification(application):
                success = False
                logger.error(
                    f"Failed staff notification for application {application.id}"
                )
            else:
                logger.info(f"Sent staff notification for application {application.id}")
        except Exception as e:
            success = False
            logger.error(
                f"Exception sending staff notification for application {application.id}: {e}"
            )

        return success
