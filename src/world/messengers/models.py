"""Models for IC missives: letters carried between personas (#3289).

``TransmissionMethod`` is the staff-tunable vocabulary of ways a letter can
travel (a messenger runner at MVP). ``Missive`` is one letter from one persona
to another; ``MissiveAttachment`` is one item or one sum of coin riding on it,
held until the recipient accepts or refuses it.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.messengers.constants import AttachmentResolution

PERSONA_MODEL = "arxii.Persona"


class TransmissionMethod(NaturalKeyMixin, SharedMemoryModel):
    """A way a letter travels, and how long it takes in game time."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(
        help_text="Fiction copy shown to players when they choose how to send a letter.",
    )
    ic_delay_minutes = models.PositiveIntegerField(
        help_text="Game-time minutes between sending and the letter arriving.",
    )
    can_carry_items = models.BooleanField(default=True)
    can_carry_coin = models.BooleanField(default=True)
    is_universal = models.BooleanField(
        default=False,
        help_text="Any character may use this method without a capability.",
    )
    required_capability = models.ForeignKey(
        "arxii.CapabilityType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Hook for a magical method: a character with this capability may use it.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Missive(SharedMemoryModel):
    """One letter from one persona to another."""

    sender_persona = models.ForeignKey(
        PERSONA_MODEL,
        on_delete=models.CASCADE,
        related_name="missives_sent",
    )
    recipient_persona = models.ForeignKey(
        PERSONA_MODEL,
        on_delete=models.CASCADE,
        related_name="missives_received",
    )
    method = models.ForeignKey(
        TransmissionMethod,
        on_delete=models.PROTECT,
        related_name="missives",
    )
    body = models.TextField()
    ic_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Game-clock time the letter was sent; null when no game clock is running.",
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    available_at = models.DateTimeField(
        db_index=True,
        help_text="Real time the letter arrives and the recipient can read it.",
    )
    arrival_notified_at = models.DateTimeField(null=True, blank=True)
    undeliverable = models.BooleanField(
        default=False,
        help_text=(
            "Write-then-suppress block: the recipient blocks the sender, so the letter "
            "is kept but never delivered. Never shown to either side."
        ),
    )
    read_at = models.DateTimeField(null=True, blank=True)
    in_reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
    )

    class Meta:
        ordering = ["-sent_at"]
        indexes = [
            models.Index(
                fields=["recipient_persona", "available_at"],
                name="missive_recipient_avail_idx",
            ),
            models.Index(
                fields=["sender_persona", "sent_at"],
                name="missive_sender_sent_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"Missive {self.pk}"


class MissiveAttachment(SharedMemoryModel):
    """One item or one sum of coin riding on a missive."""

    missive = models.ForeignKey(
        Missive,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    # PROTECT, not SET_NULL: the XOR constraint below needs item set on an item
    # attachment, and an item in transit cannot be destroyed.
    item = models.ForeignKey(
        "arxii.ItemInstance",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    coin_amount = models.PositiveBigIntegerField(null=True, blank=True)
    resolution = models.CharField(
        max_length=20,
        choices=AttachmentResolution.choices,
        default=AttachmentResolution.PENDING,
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(item__isnull=False, coin_amount__isnull=True)
                    | Q(item__isnull=True, coin_amount__isnull=False)
                ),
                name="messenger_attachment_item_xor_coin",
            ),
            models.UniqueConstraint(
                fields=["item"],
                condition=Q(resolution=AttachmentResolution.PENDING),
                name="messenger_item_in_transit_once",
            ),
        ]

    def __str__(self) -> str:
        return f"Attachment {self.pk} on missive {self.missive_id}"
