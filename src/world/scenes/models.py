from functools import cached_property
from typing import TYPE_CHECKING, Any

from django.db import models
from django.db.models import Max
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from evennia_extensions.mixins import CachedPropertiesMixin, RelatedCacheClearingMixin
from world.scenes.constants import (
    InteractionMode,
    InteractionVisibility,
    MessageContext,
    MessageMode,
    ScenePrivacyMode,
    SummaryAction,
    SummaryStatus,
)

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
    privacy_mode = models.CharField(
        max_length=20,
        choices=ScenePrivacyMode.choices,
        default=ScenePrivacyMode.PUBLIC,
        help_text="Privacy floor for all interactions in this scene",
    )
    summary = models.TextField(
        blank=True,
        help_text="Scene summary — required for ephemeral scenes, optional for others",
    )
    summary_status = models.CharField(
        max_length=20,
        choices=SummaryStatus.choices,
        default=SummaryStatus.DRAFT,
        blank=True,
        help_text="Status of collaborative summary (mainly for ephemeral scenes)",
    )

    participants = models.ManyToManyField(
        "accounts.AccountDB",
        through="SceneParticipation",
        related_name="participated_scenes",
        help_text="Accounts that have participated in this scene",
    )

    class Meta:
        ordering = ["-date_started"]

    def __str__(self) -> str:
        return f"{self.name} ({self.date_started})"

    @property
    def is_finished(self) -> bool:
        return self.date_finished is not None

    @property
    def is_public(self) -> bool:
        """Backwards-compatible check — scene is public if privacy mode is PUBLIC."""
        return self.privacy_mode == ScenePrivacyMode.PUBLIC

    @property
    def is_ephemeral(self) -> bool:
        """Whether this scene is ephemeral (content never stored)."""
        return self.privacy_mode == ScenePrivacyMode.EPHEMERAL

    @cached_property
    def participations_cached(self) -> list["SceneParticipation"]:
        """Return participations for this scene, cached."""
        return list(self.participations.select_related("account"))

    def is_owner(self, account: "AccountDB | None") -> bool:
        """Return True if ``account`` owns this scene."""
        if account is None:
            return False
        return any(
            part.account_id == account.id and part.is_owner for part in self.participations_cached
        )

    def finish_scene(self) -> None:
        """Mark the scene as finished and stop recording new messages"""
        if not self.is_finished:
            self.date_finished = timezone.now()
            self.is_active = False
            self.save()


class SceneParticipation(RelatedCacheClearingMixin, SharedMemoryModel):
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


class Persona(SharedMemoryModel):
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

    def __str__(self) -> str:
        return f"{self.name} in {self.participation.scene.name}"

    @property
    def scene(self) -> Scene:
        """Convenience access to the persona's scene."""
        return self.participation.scene


class SceneMessage(SharedMemoryModel):
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

    @cached_property
    def cached_receivers(self) -> list["Persona"]:
        """Prefetched receivers for this message."""
        return list(self.receivers.all())

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.sequence_number:
            # Auto-assign sequence number using MAX for efficiency
            max_sequence = SceneMessage.objects.filter(scene=self.scene).aggregate(
                max_seq=Max("sequence_number"),
            )["max_seq"]
            self.sequence_number = (max_sequence + 1) if max_sequence else 1
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        content = str(self.content)
        return f"{self.persona.name}: {content[:50]}..."


class SceneMessageSupplementalData(SharedMemoryModel):
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

    def __str__(self) -> str:
        return f"Supplemental data for: {self.message}"


class SceneMessageReaction(SharedMemoryModel):
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

    def __str__(self) -> str:
        return f"{self.account} reacted to {self.message} with {self.emoji}"


class Interaction(SharedMemoryModel):
    """An atomic IC interaction — one writer, one piece of content, one audience.

    Created automatically whenever a character poses, emits, says, whispers,
    shouts, or takes a mechanical action. The universal building block of RP
    recording. Scenes are optional containers; interactions exist independently.
    """

    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="interactions_written",
        help_text="The IC identity who wrote this interaction",
    )
    roster_entry = models.ForeignKey(
        "roster.RosterEntry",
        on_delete=models.CASCADE,
        related_name="interactions_written",
        help_text="The specific player — privacy binds to roster entry, not character",
    )
    persona = models.ForeignKey(
        Persona,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interactions_written",
        help_text="Disguise/alt identity if active during this interaction",
    )
    location = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="interactions_at",
        help_text="Where this interaction happened",
    )
    scene = models.ForeignKey(
        Scene,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interactions",
        help_text="Scene container if one was active",
    )
    target_personas = models.ManyToManyField(
        Persona,
        blank=True,
        related_name="interactions_targeted",
        help_text="Explicit IC targets for thread derivation",
    )
    content = models.TextField(
        help_text="The actual written text of the interaction",
    )
    mode = models.CharField(
        max_length=20,
        choices=InteractionMode.choices,
        default=InteractionMode.POSE,
        help_text="The type of IC interaction",
    )
    visibility = models.CharField(
        max_length=20,
        choices=InteractionVisibility.choices,
        default=InteractionVisibility.DEFAULT,
        help_text="Privacy override — can only escalate, never reduce",
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    sequence_number = models.PositiveIntegerField(
        help_text="Ordering within a location for chronological display",
    )

    class Meta:
        ordering = ["timestamp", "sequence_number"]
        indexes = [
            models.Index(fields=["character", "timestamp"]),
            models.Index(fields=["location", "timestamp"]),
            models.Index(fields=["scene", "sequence_number"]),
        ]

    def __str__(self) -> str:
        content_preview = str(self.content)[:50]
        return f"{self.character}: {content_preview}..."

    @property
    def cached_target_personas(self) -> list["Persona"]:
        """Target personas. Uses Prefetch(to_attr=) when available, else queries."""
        try:
            return self._cached_target_personas
        except AttributeError:
            return list(self.target_personas.all())

    @cached_target_personas.setter
    def cached_target_personas(self, value: list["Persona"]) -> None:
        """Allow Prefetch(to_attr='cached_target_personas') to set this."""
        self._cached_target_personas = value

    @property
    def cached_favorites(self) -> list["InteractionFavorite"]:
        """Favorites. Uses Prefetch(to_attr=) when available, else queries."""
        try:
            return self._cached_favorites
        except AttributeError:
            return list(self.favorites.all())

    @cached_favorites.setter
    def cached_favorites(self, value: list["InteractionFavorite"]) -> None:
        """Allow Prefetch(to_attr='cached_favorites') to set this."""
        self._cached_favorites = value

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.sequence_number:
            max_seq = Interaction.objects.filter(location=self.location).aggregate(
                max_seq=Max("sequence_number"),
            )["max_seq"]
            self.sequence_number = (max_seq + 1) if max_seq else 1
        super().save(*args, **kwargs)


class InteractionAudience(SharedMemoryModel):
    """Captures exactly who could see an interaction at creation time.

    This is the visibility ceiling — it can only shrink, never expand.
    All player-facing surfaces display the persona, never the roster entry.
    """

    interaction = models.ForeignKey(
        Interaction,
        on_delete=models.CASCADE,
        related_name="audience",
        help_text="The interaction this audience record belongs to",
    )
    roster_entry = models.ForeignKey(
        "roster.RosterEntry",
        on_delete=models.CASCADE,
        related_name="interactions_witnessed",
        help_text="The specific player who saw this interaction",
    )
    persona = models.ForeignKey(
        Persona,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interactions_witnessed",
        help_text="The IC identity they were presenting as when they saw it",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "roster_entry"],
                name="unique_audience_per_interaction",
            ),
        ]
        indexes = [
            models.Index(fields=["roster_entry", "interaction"]),
        ]

    def __str__(self) -> str:
        name = self.persona.name if self.persona else str(self.roster_entry)
        return f"{name} witnessed interaction {self.interaction_id}"


class InteractionFavorite(SharedMemoryModel):
    """Private bookmark for a cherished RP moment.

    Purely private — no other player sees what you bookmarked. Social feedback
    (kudos, pose voting, reactions) is handled by separate systems.
    """

    interaction = models.ForeignKey(
        Interaction,
        on_delete=models.CASCADE,
        related_name="favorites",
        help_text="The bookmarked interaction",
    )
    roster_entry = models.ForeignKey(
        "roster.RosterEntry",
        on_delete=models.CASCADE,
        related_name="favorited_interactions",
        help_text="The player who bookmarked this",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "roster_entry"],
                name="unique_favorite_per_interaction",
            ),
        ]

    def __str__(self) -> str:
        return f"Favorite: interaction {self.interaction_id} by {self.roster_entry}"


class SceneSummaryRevision(SharedMemoryModel):
    """A revision in the collaborative summary editing flow for ephemeral scenes.

    All author references use Persona (IC identity), never Account. Players
    editing a summary see 'Revised by The Masked Baron', not 'Revised by steve_2847'.
    """

    scene = models.ForeignKey(
        Scene,
        on_delete=models.CASCADE,
        related_name="summary_revisions",
        help_text="The ephemeral scene this revision belongs to",
    )
    persona = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        related_name="summary_revisions",
        help_text="Who submitted this revision (IC identity, never account)",
    )
    content = models.TextField(
        help_text="The summary text for this revision",
    )
    action = models.CharField(
        max_length=20,
        choices=SummaryAction.choices,
        help_text="Whether this is a submission, edit, or agreement",
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.persona.name} {self.action} summary for {self.scene.name}"
