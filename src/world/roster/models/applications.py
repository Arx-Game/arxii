"""
RosterApplication model for handling character applications.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from world.roster.managers import RosterApplicationManager
from world.roster.models.choices import ApplicationStatus, RosterType

if TYPE_CHECKING:
    from evennia_extensions.models import PlayerData
    from world.roster.models.tenures import RosterTenure
    from world.roster.types import PolicyInfo


class RosterApplication(SharedMemoryModel):
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
        "character_sheets.CharacterSheet",
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
        Roster = apps.get_model("roster", "Roster")

        entry = self.character.roster_entry

        # A returning player is re-seated onto their own past tenure rather than
        # given a new one (#2728 §7) — minting a second row would announce them as
        # "2nd player of X" when they are the same person, which is exactly what
        # the anonymity numbering is not for. Approval is the decision point, so
        # rival applications simply never reach here.
        tenure = entry.tenures.filter(player_data=self.player_data).order_by("-start_date").first()
        if tenure is not None:
            tenure.end_date = None
            tenure.applied_date = self.applied_date
            tenure.approved_date = timezone.now()
            tenure.approved_by = staff_player_data
            tenure.save(
                update_fields=["end_date", "applied_date", "approved_date", "approved_by"],
            )
        else:
            # max()+1, not count()+1: an ended tenure still occupies its number, and
            # counting would reissue it after any row is ever removed.
            highest = entry.tenures.aggregate(models.Max("player_number"))["player_number__max"]
            tenure = RosterTenure.objects.create(
                player_data=self.player_data,
                roster_entry=entry,
                player_number=(highest or 0) + 1,
                start_date=timezone.now(),
                applied_date=self.applied_date,
                approved_date=timezone.now(),
                approved_by=staff_player_data,
            )

        # Someone is playing this character now, so it leaves the shelf it was
        # offered from. The authored activity_requirement lives on the entry and is
        # untouched by the move (#2728) — that is why it isn't on the Roster.
        entry.move_to_roster(Roster.objects.get(roster_type=RosterType.ACTIVE))
        entry.__dict__.pop("cached_tenures", None)

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
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["player_data", "character"],
                condition=models.Q(status=ApplicationStatus.PENDING),
                name="unique_pending_application_per_player_character",
            ),
        ]
        ordering: ClassVar[list[str]] = ["-applied_date"]
        verbose_name = "Roster Application"
        verbose_name_plural = "Roster Applications"
