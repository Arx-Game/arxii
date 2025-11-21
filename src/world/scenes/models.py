from functools import cached_property
from typing import TYPE_CHECKING

from django.db import models
from django.db.models import Max
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from evennia_extensions.mixins import CachedPropertiesMixin, RelatedCacheClearingMixin
from world.scenes.constants import MessageContext, MessageMode

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB


class Scene(CachedPropertiesMixin, SharedMemoryModel):
    """
    A scene is a recorded roleplay session that captures messages from participants.
    Similar to dominion.RPEvent but focused on message recording and scene management.
    """

    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    location = models.ForeignKey(
        "objects.ObjectDB",
        blank=True,
        null=True,
        related_name="scenes_held",
        on_delete=models.SET_NULL,
        help_text="The room/location where this scene takes place",
    )
    date_started = models.DateTimeField(auto_now_add=True)
    date_finished = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_public = models.BooleanField(default=True)

    participants = models.ManyToManyField(
        "accounts.AccountDB",
        through="SceneParticipation",
        related_name="participated_scenes",
        help_text="Accounts that have participated in this scene",
    )

    class Meta:
        ordering = ["-date_started"]

    def __str__(self):
        return f"{self.name} ({self.date_started})"

    @property
    def is_finished(self):
        return self.date_finished is not None

    @cached_property
    def participations_cached(self):
        """Return participations for this scene, cached."""
        return list(self.participations.select_related("account"))

    def is_owner(self, account: "AccountDB | None") -> bool:
        """Return True if ``account`` owns this scene."""
        if account is None:
            return False
        return any(
            part.account_id == account.id and part.is_owner
            for part in self.participations_cached
        )

    def finish_scene(self):
        """Mark the scene as finished and stop recording new messages"""
        if not self.is_finished:
            self.date_finished = timezone.now()
            self.is_active = False
            self.save()


class SceneParticipation(RelatedCacheClearingMixin, models.Model):
    """
    Links accounts to scenes they participate in
    """

    scene = models.ForeignKey(
        Scene,
        on_delete=models.CASCADE,
        related_name="participations",
    )
    account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="scene_participations",
    )
    is_gm = models.BooleanField(default=False)
    is_owner = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(blank=True, null=True)

    related_cache_fields = ["scene"]

    class Meta:
        unique_together = ["scene", "account"]


class Persona(models.Model):
    """Identity a participant uses within a scene."""

    participation = models.ForeignKey(
        SceneParticipation,
        on_delete=models.CASCADE,
        related_name="personas",
    )

    name = models.CharField(max_length=255)
    is_fake_name = models.BooleanField(
        default=False,
        help_text="Whether this persona uses a fake name",
    )
    description = models.TextField(blank=True)
    thumbnail_url = models.URLField(blank=True, max_length=500)

    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="scene_personas",
        help_text="The character this persona represents, if any",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["participation", "name"]

    def __str__(self):
        return f"{self.name} in {self.participation.scene.name}"

    @property
    def scene(self):
        """Convenience access to the persona's scene."""
        return self.participation.scene


class SceneMessage(models.Model):
    """
    A message sent during a scene by a specific persona
    """

    scene = models.ForeignKey(Scene, on_delete=models.CASCADE, related_name="messages")
    persona = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        related_name="sent_messages",
    )

    content = models.TextField()
    context = models.CharField(
        max_length=20,
        choices=MessageContext.choices,
        default=MessageContext.PUBLIC,
    )
    mode = models.CharField(
        max_length=20,
        choices=MessageMode.choices,
        default=MessageMode.POSE,
    )

    receivers = models.ManyToManyField(
        Persona,
        blank=True,
        related_name="received_messages",
        help_text="Specific personas who should receive this message. "
        "If empty, all scene participants receive it",
    )

    timestamp = models.DateTimeField(auto_now_add=True)
    sequence_number = models.PositiveIntegerField()

    class Meta:
        ordering = ["sequence_number"]
        unique_together = ["scene", "sequence_number"]

    def save(self, *args, **kwargs):
        if not self.sequence_number:
            # Auto-assign sequence number using MAX for efficiency
            max_sequence = SceneMessage.objects.filter(scene=self.scene).aggregate(
                max_seq=Max("sequence_number"),
            )["max_seq"]
            self.sequence_number = (max_sequence + 1) if max_sequence else 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.persona.name}: {self.content[:50]}..."


class SceneMessageSupplementalData(models.Model):
    """
    Supplemental data for messages to avoid bloating the main SceneMessage table.
    This will store additional metadata as JSON that doesn't need to be queried often.
    Examples: formatting data, attached media, special effects, etc.
    """

    message = models.OneToOneField(
        SceneMessage,
        on_delete=models.CASCADE,
        related_name="supplemental_data",
        primary_key=True,
    )
    data = models.JSONField(default=dict)

    def __str__(self):
        return f"Supplemental data for: {self.message}"


class SceneMessageReaction(models.Model):
    """Reaction to a scene message."""

    message = models.ForeignKey(
        SceneMessage,
        on_delete=models.CASCADE,
        related_name="reactions",
    )
    account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="scene_message_reactions",
    )
    emoji = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["message", "account", "emoji"]

    def __str__(self):
        return f"{self.account} reacted to {self.message} with {self.emoji}"
