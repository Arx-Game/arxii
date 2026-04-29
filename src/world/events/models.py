from django.db import models
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from core.mixins import DiscriminatorMixin
from world.events.constants import EventStatus, InvitationTargetType
from world.game_clock.constants import TimePhase


class Event(SharedMemoryModel):
    """A scheduled RP gathering — ball, meeting, ritual, training session.

    Events handle scheduling, access control, and room state. Scenes handle
    RP recording. An Event spawns a Scene when RP begins.
    """

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    location = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        on_delete=models.PROTECT,
        related_name="events",
        help_text="The room where this event takes place",
    )
    status = models.CharField(
        max_length=20,
        choices=EventStatus.choices,
        default=EventStatus.DRAFT,
        db_index=True,
    )
    is_public = models.BooleanField(
        default=True,
        help_text="Public events are visible on the calendar to everyone",
    )

    # Scheduling — real time is primary, IC time derived then adjustable
    scheduled_real_time = models.DateTimeField(
        help_text="The OOC date/time players schedule for",
    )
    scheduled_ic_time = models.DateTimeField(
        help_text="IC datetime — derived from game clock, then adjustable",
    )
    time_phase = models.CharField(
        max_length=10,
        choices=TimePhase.choices,
        default=TimePhase.DAY,
        help_text="Time-of-day phase for the event (scene time freezes here)",
    )

    # Lifecycle
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "scheduled_real_time"]),
            models.Index(fields=["location", "scheduled_real_time"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_status_display()})"

    @property
    def is_active(self) -> bool:
        return self.status == EventStatus.ACTIVE

    @property
    def is_upcoming(self) -> bool:
        return self.status == EventStatus.SCHEDULED

    # These cached_property methods serve as fallbacks when instances are accessed
    # outside the ViewSet (admin, shell, service functions). The ViewSet uses
    # Prefetch(to_attr="hosts_cached") which writes directly to __dict__,
    # taking precedence over the cached_property descriptor.
    @cached_property
    def hosts_cached(self) -> list["EventHost"]:
        return list(self.hosts.select_related("persona"))

    @cached_property
    def invitations_cached(self) -> list["EventInvitation"]:
        return list(
            self.invitations.select_related(
                "target_persona", "target_organization", "target_society"
            )
        )


class EventHost(SharedMemoryModel):
    """A host persona for an event. Multiple hosts supported."""

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="hosts",
    )
    persona = models.ForeignKey(
        "scenes.Persona",
        null=True,
        on_delete=models.SET_NULL,
        related_name="hosted_events",
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="The primary host is the 'face' of the event on listings",
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "persona"],
                condition=models.Q(persona__isnull=False),
                name="unique_event_host",
            ),
        ]

    def __str__(self) -> str:
        persona_name = self.persona.name if self.persona else "(deleted)"
        return f"{persona_name} hosting {self.event.name}"


class EventInvitation(DiscriminatorMixin, SharedMemoryModel):
    """An invitation to an event — can target a persona, organization, or society."""

    DISCRIMINATOR_FIELD = "target_type"
    DISCRIMINATOR_MAP = {
        InvitationTargetType.PERSONA: "target_persona",
        InvitationTargetType.ORGANIZATION: "target_organization",
        InvitationTargetType.SOCIETY: "target_society",
    }

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    target_type = models.CharField(
        max_length=20,
        choices=InvitationTargetType.choices,
    )
    target_persona = models.ForeignKey(
        "scenes.Persona",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="event_invitations",
    )
    target_organization = models.ForeignKey(
        "societies.Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="event_invitations",
    )
    target_society = models.ForeignKey(
        "societies.Society",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="event_invitations",
    )
    can_bring_guests = models.BooleanField(default=False)
    invited_at = models.DateTimeField(auto_now_add=True)
    invited_by = models.ForeignKey(
        "scenes.Persona",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invitations_sent",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "target_type", "target_persona"],
                condition=models.Q(target_type=InvitationTargetType.PERSONA),
                name="unique_persona_invitation",
            ),
            models.UniqueConstraint(
                fields=["event", "target_type", "target_organization"],
                condition=models.Q(target_type=InvitationTargetType.ORGANIZATION),
                name="unique_organization_invitation",
            ),
            models.UniqueConstraint(
                fields=["event", "target_type", "target_society"],
                condition=models.Q(target_type=InvitationTargetType.SOCIETY),
                name="unique_society_invitation",
            ),
        ]

    def __str__(self) -> str:
        return f"Invitation to {self.event.name}: {self.get_active_target_name()}"


class EventModification(SharedMemoryModel):
    """Room modifications applied while an event is ACTIVE.

    Stub model — only room_description_overlay is functional for MVP.
    Full design of additional modification types requires a dedicated
    brainstorming session before expanding this schema.
    """

    event = models.OneToOneField(
        Event,
        on_delete=models.CASCADE,
        related_name="modification",
    )
    room_description_overlay = models.TextField(
        blank=True,
        help_text="Text that augments the room description while event is active",
    )

    def __str__(self) -> str:
        return f"Modifications for {self.event.name}"
