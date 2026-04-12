"""GM system models."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.gm.constants import GMLevel


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
        help_text="When this account was approved as a GM.",
    )
    approved_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Staff account that approved the GM application.",
    )

    class Meta:
        verbose_name = "GM Profile"
        verbose_name_plural = "GM Profiles"

    def __str__(self) -> str:
        return f"GMProfile({self.account.username}, {self.get_level_display()})"
