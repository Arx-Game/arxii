"""GM system models."""

from django.db import models
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from world.gm.constants import GMApplicationStatus, GMLevel


class GMProfile(SharedMemoryModel):
    """A player's GM identity: their level, stats, and approval date.

    One per account. Created when a GMApplication is approved.
    The account FK is the anchor — GM level checks query this model.
    """

    account = models.OneToOneField(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="gm_profile",
    )
    level = models.CharField(
        max_length=20,
        choices=GMLevel.choices,
        default=GMLevel.STARTING,
        db_index=True,
    )
    approved_at = models.DateTimeField(
        default=timezone.now,
        help_text="When this account was approved as a GM.",
    )
    approved_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Staff account that approved the GM application.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "GM Profile"
        verbose_name_plural = "GM Profiles"

    def __str__(self) -> str:
        return f"GMProfile({self.account.username}, {self.get_level_display()})"


class GMApplication(SharedMemoryModel):
    """A player's application to become a GM.

    Freeform text field for the applicant to describe what they want to GM,
    which players they'd run for, and what stories they'd tell. Staff reviews
    and responds via staff_response. On approval, a GMProfile is created.
    """

    account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="gm_applications",
    )
    application_text = models.TextField(
        help_text=(
            "Freeform: what the applicant wants to GM, who they'd run for, "
            "what stories they'd tell."
        ),
    )
    staff_response = models.TextField(
        blank=True,
        default="",
        help_text="Staff feedback on the application.",
    )
    status = models.CharField(
        max_length=20,
        choices=GMApplicationStatus.choices,
        default=GMApplicationStatus.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Staff account that reviewed this application.",
    )

    class Meta:
        verbose_name = "GM Application"
        verbose_name_plural = "GM Applications"

    def __str__(self) -> str:
        return f"GMApplication({self.account.username}, {self.status})"
