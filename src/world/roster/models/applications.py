"""
RosterApplication model for handling character applications.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils import timezone
from evennia.objects.models import ObjectDB

from world.roster.managers import RosterApplicationManager
from world.roster.models.choices import ApplicationStatus

if TYPE_CHECKING:
    from evennia_extensions.models import PlayerData
    from world.roster.models.tenures import RosterTenure
    from world.roster.types import PolicyInfo


class RosterApplication(models.Model):
    """
    Tracks applications before they become tenures.
    Separate from tenure to keep application data clean.
    """

    # Custom manager
    objects = RosterApplicationManager()

    player_data = models.ForeignKey(
        "evennia_extensions.PlayerData",
        on_delete=models.CASCADE,
        related_name="applications",
    )
    character = models.ForeignKey(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="applications",
    )

    # Application status
    status = models.CharField(
        max_length=20,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.PENDING,
    )

    # Dates
    applied_date = models.DateTimeField(auto_now_add=True)
    reviewed_date = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "evennia_extensions.PlayerData",
        null=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_applications",
    )

    # Application content
    application_text = models.TextField(help_text="Why player wants this character")
    review_notes = models.TextField(blank=True, help_text="Staff notes on application")

    def approve(self, staff_player_data: PlayerData) -> RosterTenure | bool:
        """Approve application and create tenure"""
        if self.status != ApplicationStatus.PENDING:
            return False

        # Import here to avoid circular imports
        from django.apps import apps

        RosterTenure = apps.get_model("roster", "RosterTenure")

        # Create the tenure
        player_number = self.character.roster_entry.tenures.count() + 1
        tenure = RosterTenure.objects.create(
            player_data=self.player_data,
            roster_entry=self.character.roster_entry,
            player_number=player_number,
            start_date=timezone.now(),
            applied_date=self.applied_date,
            approved_date=timezone.now(),
            approved_by=staff_player_data,
        )

        # Update application
        self.status = ApplicationStatus.APPROVED
        self.reviewed_date = timezone.now()
        self.reviewed_by = staff_player_data
        self.save()

        # Send approval email
        try:
            from world.roster.email_service import RosterEmailService

            RosterEmailService.send_application_approved(self, tenure)
        except Exception as exc:
            logging.exception(
                "Failed to send approval email for roster application %s",
                self.pk,
                exc_info=exc,
            )

        return tenure

    def get_policy_review_info(self) -> PolicyInfo:
        """
        Get comprehensive policy information for reviewers.

        Returns a dict with all policy considerations for this application.
        """
        # Import at method level to avoid circular imports with DRF serializers
        from world.roster.policy_service import RosterPolicyService

        return RosterPolicyService.get_comprehensive_policy_info(self)

    def deny(self, staff_player_data: PlayerData, reason: str = "") -> bool:
        """Deny application"""
        if self.status != ApplicationStatus.PENDING:
            return False

        self.status = ApplicationStatus.DENIED
        self.reviewed_date = timezone.now()
        self.reviewed_by = staff_player_data
        if reason:
            self.review_notes = reason
        self.save()

        # Send denial email
        try:
            from world.roster.email_service import RosterEmailService

            RosterEmailService.send_application_denied(self)
        except Exception as exc:
            logging.exception(
                "Failed to send denial email for roster application %s",
                self.pk,
                exc_info=exc,
            )

        return True

    def withdraw(self) -> bool:
        """Player withdraws their own application"""
        if self.status != ApplicationStatus.PENDING:
            return False

        self.status = ApplicationStatus.WITHDRAWN
        self.reviewed_date = timezone.now()
        self.save()
        return True

    def __str__(self) -> str:
        return (
            f"{self.player_data.account.username} applying for "
            f"{self.character.name} ({self.status})"
        )

    class Meta:
        unique_together: ClassVar[list[str]] = [
            "player_data",
            "character",
        ]  # One app per player per char
        ordering: ClassVar[list[str]] = ["-applied_date"]
        verbose_name = "Roster Application"
        verbose_name_plural = "Roster Applications"
