from functools import cached_property
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
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
    PersonaType,
    ScenePrivacyMode,
    SummaryAction,
    SummaryStatus,
)

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.scenes.place_models import InteractionReceiver


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
    """A face the character shows the world.

    Every character has at least one primary persona (their 'real' identity).
    Established personas are persistent alter egos with their own reputation
    and relationships. Temporary personas are throwaway disguises.
    """

    character_identity = models.ForeignKey(
        "character_sheets.CharacterIdentity",
        on_delete=models.CASCADE,
        related_name="personas",
        help_text="The real character behind this persona",
    )
    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="personas",
        help_text="The character object (denormalized from character_identity for queries)",
    )
    name = models.CharField(max_length=255, help_text="Display name for this persona")
    colored_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name with color formatting codes",
    )
    description = models.TextField(blank=True, help_text="Physical description text")
    thumbnail_url = models.URLField(blank=True, max_length=500)
    thumbnail = models.ForeignKey(
        "evennia_extensions.PlayerMedia",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="persona_thumbnails",
        help_text="Visual representation",
    )
    persona_type = models.CharField(
        max_length=20,
        choices=PersonaType.choices,
        default=PersonaType.TEMPORARY,
        help_text="PRIMARY = real identity, ESTABLISHED = persistent alter ego, "
        "TEMPORARY = throwaway disguise",
    )
    is_fake_name = models.BooleanField(
        default=False,
        help_text="True when this persona obscures the character's identity",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character_identity"],
                condition=models.Q(persona_type="primary"),
                name="unique_primary_persona",
            ),
            models.UniqueConstraint(
                fields=["character_identity", "name"],
                name="unique_persona_name_per_character",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_persona_type_display()})"

    def clean(self) -> None:
        super().clean()
        if (
            self.character_identity_id
            and self.character_id
            and self.character_identity.character_id != self.character_id
        ):
            raise ValidationError(
                {"character": "Character must match character_identity.character."}
            )

    @property
    def is_established_or_primary(self) -> bool:
        """Whether this persona can have relationships, reputation, legend."""
        return self.persona_type in (PersonaType.PRIMARY, PersonaType.ESTABLISHED)


class PersonaDiscovery(SharedMemoryModel):
    """Records that a character discovered two personas are the same person.

    Stores only raw discovery pairs. A service function handles resolution
    logic (what name to display, transitive chains, etc.).
    """

    persona_a = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        related_name="discoveries_as_a",
    )
    persona_b = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        related_name="discoveries_as_b",
    )
    discovered_by = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="persona_discoveries",
        help_text="The character who figured out these two personas are the same person",
    )
    discovered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["persona_a", "persona_b", "discovered_by"],
                name="unique_persona_discovery",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.discovered_by} knows {self.persona_a.name} = {self.persona_b.name}"


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

    persona = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        related_name="interactions_written",
        help_text="How the writer appeared at this moment. Always set — every "
        "interaction has a persona, even if it's just the character's primary persona.",
    )
    scene = models.ForeignKey(
        Scene,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interactions",
        help_text="Scene container if one was active",
    )
    place = models.ForeignKey(
        "scenes.Place",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interactions",
        help_text="Sub-location where this interaction occurred",
    )
    target_personas = models.ManyToManyField(
        Persona,
        blank=True,
        through="InteractionTargetPersona",
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

    class Meta:
        # NO ordering — cursor pagination handles it. Default ordering on a
        # partitioned table forces cross-partition merge-sorts on every query.
        indexes = [
            models.Index(fields=["persona", "timestamp"]),
            models.Index(fields=["scene", "timestamp"]),
            # Fast exclusion of very_private for staff queryset
            models.Index(
                fields=["timestamp"],
                name="interaction_very_private_idx",
                condition=models.Q(visibility="very_private"),
            ),
            # Organic grid RP (no scene) queries
            models.Index(
                fields=["timestamp"],
                name="interaction_no_scene_idx",
                condition=models.Q(scene__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        content_preview = str(self.content)[:50]
        return f"{self.persona.name}: {content_preview}..."

    @property
    def cached_receivers(self) -> list["InteractionReceiver"]:
        """Receiver records. Uses Prefetch(to_attr=) when available, else queries."""
        try:
            return self._cached_receivers
        except AttributeError:
            from world.scenes.place_models import InteractionReceiver  # noqa: PLC0415

            return list(InteractionReceiver.objects.filter(interaction=self))

    @cached_receivers.setter
    def cached_receivers(self, value: list["InteractionReceiver"]) -> None:
        """Allow Prefetch(to_attr='cached_receivers') to set this."""
        self._cached_receivers = value

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


class InteractionFavorite(SharedMemoryModel):
    """Private bookmark for a cherished RP moment.

    Purely private — no other player sees what you bookmarked. Social feedback
    (kudos, pose voting, reactions) is handled by separate systems.
    """

    interaction = models.ForeignKey(
        Interaction,
        on_delete=models.CASCADE,
        related_name="favorites",
        db_constraint=False,
        help_text="The bookmarked interaction",
    )
    timestamp = models.DateTimeField(
        help_text="Denormalized from interaction — required for composite FK "
        "with partitioned table",
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

    def clean(self) -> None:
        super().clean()
        if (
            self.interaction_id
            and self.timestamp
            and hasattr(self, "interaction")
            and self.interaction.timestamp != self.timestamp
        ):
            msg = "timestamp must match interaction.timestamp"
            raise ValidationError({"timestamp": msg})


class InteractionTargetPersona(SharedMemoryModel):
    """Explicit through model for interaction target personas.

    Needed for composite FK compatibility with partitioned Interaction table.
    """

    interaction = models.ForeignKey(
        Interaction,
        on_delete=models.CASCADE,
        related_name="interaction_targets",
        db_constraint=False,
    )
    timestamp = models.DateTimeField(
        help_text="Denormalized from interaction for partitioned table FK",
    )
    persona = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        related_name="targeted_in_interactions",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "persona"],
                name="unique_target_per_interaction",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if (
            self.interaction_id
            and self.timestamp
            and hasattr(self, "interaction")
            and self.interaction.timestamp != self.timestamp
        ):
            msg = "timestamp must match interaction.timestamp"
            raise ValidationError({"timestamp": msg})


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


# Import place_models for Django model discovery
from world.scenes.place_models import InteractionReceiver, Place, PlacePresence  # noqa: E402, F401
