from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.narrative.constants import NarrativeCategory

_STR_PREVIEW_LEN = 40


class NarrativeMessage(SharedMemoryModel):
    """A single IC message delivered to one or more characters.

    The message itself is immutable after send. Per-recipient state
    (delivered, acknowledged) lives on NarrativeMessageDelivery.
    """

    body = models.TextField(
        help_text="IC content shown to recipients.",
    )
    ooc_note = models.TextField(
        blank=True,
        help_text=(
            "OOC context visible to staff and GMs with access to the "
            "recipient's character — explains why this message was sent, "
            "what it's about, etc. Not shown to players in-character."
        ),
    )
    category = models.CharField(
        max_length=20,
        choices=NarrativeCategory.choices,
    )
    sender_account = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="narrative_messages_sent",
        help_text="Null = automated/system-sourced.",
    )

    # Optional context FKs — populated when a narrative message is produced
    # by the stories system. Consumers of the message can use these to
    # render story-log entries, link to the related story, etc.
    related_story = models.ForeignKey(
        "stories.Story",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="narrative_messages",
    )
    related_beat_completion = models.ForeignKey(
        "stories.BeatCompletion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="narrative_messages",
    )
    related_episode_resolution = models.ForeignKey(
        "stories.EpisodeResolution",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="narrative_messages",
    )

    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["category", "-sent_at"]),
            models.Index(fields=["sender_account", "-sent_at"]),
        ]

    def __str__(self) -> str:
        truncated = len(self.body) > _STR_PREVIEW_LEN
        preview = self.body[:_STR_PREVIEW_LEN] + ("..." if truncated else "")
        return f"NarrativeMessage({self.category}) {preview}"


class NarrativeMessageDelivery(SharedMemoryModel):
    """Per-recipient delivery state for a NarrativeMessage.

    One row per (message, character_sheet) pair. A single message can
    fan out to many recipients (e.g., a GM sends a covenant-wide message
    to 5 of 8 members — that's one NarrativeMessage and 5 Delivery rows).
    """

    message = models.ForeignKey(
        NarrativeMessage,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    recipient_character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="narrative_message_deliveries",
    )
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Timestamp when the message was pushed to the character's puppeted "
            "session. Null until online delivery or login catch-up delivers it."
        ),
    )
    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Timestamp when the player acknowledged having seen the message. "
            "Null until the player marks it read. Used to distinguish 'unread' "
            "in future UI work."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "recipient_character_sheet"],
                name="unique_delivery_per_message_per_recipient",
            )
        ]
        indexes = [
            models.Index(fields=["recipient_character_sheet", "delivered_at"]),
            models.Index(fields=["recipient_character_sheet", "acknowledged_at"]),
        ]

    def __str__(self) -> str:
        state = "delivered" if self.delivered_at else "queued"
        return (
            f"NarrativeMessageDelivery(msg=#{self.message_id}, "
            f"sheet=#{self.recipient_character_sheet_id}, {state})"
        )
