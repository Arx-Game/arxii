"""GM system models."""

from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, UniqueConstraint
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from world.gm.constants import GMApplicationStatus, GMLevel, GMTableStatus
from world.scenes.constants import PersonaType


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
    last_active_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Stubbed — will be stamped by future story-update activity hooks.",
    )

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
        constraints = [
            UniqueConstraint(
                fields=["account"],
                condition=Q(status="pending"),
                name="unique_pending_gm_application_per_account",
            ),
        ]

    def __str__(self) -> str:
        return f"GMApplication({self.account.username}, {self.status})"


class GMTable(SharedMemoryModel):
    """A GM's working group — players engaging with a set of stories."""

    gm = models.ForeignKey(
        "gm.GMProfile",
        on_delete=models.PROTECT,
        related_name="tables",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=GMTableStatus.choices,
        default=GMTableStatus.ACTIVE,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "GM Table"
        verbose_name_plural = "GM Tables"

    def __str__(self) -> str:
        return f"GMTable({self.name}, gm={self.gm.account.username})"


class GMTableMembership(SharedMemoryModel):
    """A player's presence at a GM table, pinned to a specific persona.

    Anchors on Persona rather than CharacterSheet because:
    - The persona is the IC face other players see at the table
    - Pinning prevents drift when the player wears a temporary mask in scenes
    - Membership history can outlive a persona via soft-leave (left_at)

    Note: persona.character_sheet remains walkable, so this is NOT a
    privacy mechanism. Staff and any caller with ORM access can still
    derive the underlying character. Privacy is enforced at the
    serializer/view layer, not at the schema level.

    Soft-leave via left_at. The unique constraint ensures only one active
    membership per (table, persona) — historical (left) memberships can
    coexist with current ones.
    """

    table = models.ForeignKey(
        "gm.GMTable",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.PROTECT,
        related_name="gm_table_memberships",
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = "GM Table Membership"
        verbose_name_plural = "GM Table Memberships"
        constraints = [
            UniqueConstraint(
                fields=["table", "persona"],
                condition=Q(left_at__isnull=True),
                name="unique_active_gm_table_membership",
            ),
        ]

    def clean(self) -> None:
        if self.persona_id and self.persona.persona_type == PersonaType.TEMPORARY:
            msg = (
                "A temporary persona cannot join a GM table — use a primary or established persona."
            )
            raise ValidationError(msg)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Run full_clean() on save to enforce TEMPORARY persona rejection.

        The clean() method is otherwise only invoked during form validation,
        which would let direct ORM calls (``Model.objects.create()`` / raw
        ``.save()``) bypass the rule.
        """
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"GMTableMembership({self.table.name}, {self.persona.name})"
