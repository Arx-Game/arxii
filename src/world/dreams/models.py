"""Dream realm models — the parallel dream layer on the room graph."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import CachedAllMixin

# App-qualified model path repeated across FK references; centralized for dedup.
_ROOM_PROFILE_MODEL = "arxii.RoomProfile"


class DreamReflectionManager(CachedAllMixin, models.Manager):
    """Manager with cached_all() and a for_waking_room convenience lookup."""

    def for_waking_room(self, room):
        """Return the active DreamReflection for a waking room, or None.

        Args:
            room: An ObjectDB room instance (the physical waking room), or
                None for a character with no location. RoomProfile shares
                ObjectDB's pk (#2608), so the room's own pk is the profile
                id — no profile lookup needed here.

        Returns:
            The active DreamReflection for this room, or None if no
            active reflection exists.
        """
        if room is None:
            return None
        return (
            self.filter(waking_room_id=room.pk, is_active=True)
            .select_related("dream_room__objectdb", "descent_target__objectdb")
            .first()
        )


class DreamReflection(SharedMemoryModel):
    """Links a physical room to its dream-layer reflection.

    Each physical room may have an optional dream reflection — a real
    ObjectDB room that sleeping/unconscious characters perceive instead
    of the waking room. Dreamers in the same physical room share the
    same dream room, so they can interact.

    Not every room needs a reflection. Rooms without one fall back to
    the liminal placeholder room (#2287's ``ensure_dream_room``).
    """

    waking_room = models.OneToOneField(
        _ROOM_PROFILE_MODEL,
        on_delete=models.CASCADE,
        related_name="dream_reflection",
    )
    dream_room = models.OneToOneField(
        _ROOM_PROFILE_MODEL,
        on_delete=models.PROTECT,
        related_name="reflection_of",
    )
    descent_target = models.ForeignKey(
        _ROOM_PROFILE_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="descent_source",
        help_text="Deep dreaming room entered from this reflection's dream room.",
    )
    is_active = models.BooleanField(default=True)

    objects = DreamReflectionManager()

    class Meta:
        verbose_name = "Dream Reflection"
        verbose_name_plural = "Dream Reflections"

    def __str__(self) -> str:
        return f"Dream of {self.waking_room}"


class DreamPerilConfig(SharedMemoryModel):
    """Singleton config for Dream Peril collapse resolution (#2290).

    Stores the resist check type and difficulty used when a dreamer's
    mental fatigue collapses while dreamside. The resolver calls
    ``select_consequence`` directly (not via ``_resolve_peril_via_pool``
    which requires a staged ConditionInstance).
    """

    resist_check_type = models.ForeignKey(
        "arxii.CheckType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dream_peril_configs",
        help_text="Check type rolled for Dream Peril resistance.",
    )
    resist_difficulty = models.PositiveIntegerField(
        default=20,
        help_text="Target difficulty for the Dream Peril resist check.",
    )

    class Meta:
        verbose_name = "Dream Peril Config"
        verbose_name_plural = "Dream Peril Configs"

    def __str__(self) -> str:
        return "Dream Peril Config"


class DreamwalkPresence(SharedMemoryModel):
    """A dreamer whose perception is anchored to another dreamer's dreamspace.

    Replaces the pre-#3003 ``ndb.dreamwalk_destination`` stash, which was
    process-local (a reload stranded the walker) and unqueryable (no surface
    could answer "who is dreaming with me"). Anchored on the host *sheet*
    rather than a room: you dreamwalk to a person, so the walker follows a
    host who moves, and there is no dependency on the host's room having a
    RoomProfile row.
    """

    dreamer = models.OneToOneField(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="dreamwalk_presence",
        help_text="The dreamwalker whose perception is displaced.",
    )
    host = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="dream_visitors",
        help_text="The dreamer whose dreamspace the walker perceives.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["pk"]
        verbose_name = "Dreamwalk Presence"
        verbose_name_plural = "Dreamwalk Presences"

    def __str__(self) -> str:
        return f"{self.dreamer} dreamwalking to {self.host}"
