"""Portal travel anchors — physical waypoints for technique-driven travel (#2222).

``PortalAnchorKind`` is a staff-authored catalog of anchor media (Mirror,
Doorway, etc.) carrying narrative arrival/departure verbs. ``PortalAnchor`` is
a concrete anchor installed in a specific room; a ``Technique`` marked with
``travel_anchor_kind`` (see ``models/techniques.py``) is a portal-travel
technique that moves the caster between anchors of that kind.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin

ROOM_PROFILE_MODEL = "evennia_extensions.RoomProfile"
PERSONA_MODEL = "scenes.Persona"


class PortalAnchorKind(NaturalKeyMixin, SharedMemoryModel):
    """A staff-authored medium of portal travel (e.g. "Mirror").

    ``Technique.travel_anchor_kind`` points here to mark a technique as a
    portal-travel technique through this anchor medium.
    """

    name = models.CharField(
        max_length=80,
        unique=True,
        help_text="Display name for this anchor kind (e.g. 'Mirror').",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of this anchor kind.",
    )
    arrival_verb = models.CharField(
        max_length=120,
        default="steps out of",
        help_text="Verb phrase narrating arrival through an anchor of this kind.",
    )
    departure_verb = models.CharField(
        max_length=120,
        default="steps into",
        help_text="Verb phrase narrating departure through an anchor of this kind.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["name"]
        verbose_name = "Portal Anchor Kind"
        verbose_name_plural = "Portal Anchor Kinds"

    def __str__(self) -> str:
        return self.name


class PortalAnchorQuerySet(models.QuerySet):
    """Custom queryset for PortalAnchor with soft-delete helpers."""

    def active(self) -> PortalAnchorQuerySet:
        """Return only anchors where dissolved_at IS NULL (i.e. not dissolved)."""
        return self.filter(dissolved_at__isnull=True)


class PortalAnchor(SharedMemoryModel):
    """A concrete portal anchor installed in a specific room.

    ``dissolved_at`` is set when the anchor is dissolved; null means active.
    Dissolution is a soft-delete — the row and all story-significant data are
    preserved. Use ``.active()`` on the queryset to exclude dissolved anchors.
    Only one active anchor of a given kind may exist per room at a time
    (enforced by the partial unique constraint below); dissolving an anchor
    frees the room to receive a fresh install of the same kind.
    """

    room_profile = models.ForeignKey(
        ROOM_PROFILE_MODEL,
        on_delete=models.CASCADE,
        related_name="portal_anchors",
        help_text="The room this anchor is installed in.",
    )
    kind = models.ForeignKey(
        PortalAnchorKind,
        on_delete=models.PROTECT,
        related_name="anchors",
        help_text="The medium of this anchor (e.g. Mirror, Doorway).",
    )
    name = models.CharField(
        max_length=120,
        help_text="Descriptive name for this specific anchor (e.g. 'a tall silvered mirror').",
    )
    is_network_open = models.BooleanField(
        default=True,
        help_text="Whether this anchor is open to travel from other anchors of the same kind.",
    )
    installed_by = models.ForeignKey(
        PERSONA_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Persona who installed this anchor, if known.",
    )
    installed_at = models.DateTimeField(auto_now_add=True)
    dissolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the anchor is dissolved; null = active.",
    )
    fixture_key = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        help_text=(
            "Permanent stable identifier for authored (exported) portal anchor installs, "
            "e.g. 'arx-city/golden-hart-taproom/mirror' (#2451). Set when installed via "
            "the staff world-builder canvas; NULL for player-installed/test anchors."
        ),
    )

    objects = PortalAnchorQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room_profile", "kind"],
                condition=models.Q(dissolved_at__isnull=True),
                name="portal_anchor_unique_active_room_kind",
            ),
        ]
        ordering = ["room_profile_id", "kind_id", "name"]
        verbose_name = "Portal Anchor"
        verbose_name_plural = "Portal Anchors"

    def __str__(self) -> str:
        return f"{self.name} ({self.kind}) @ room {self.room_profile_id}"
