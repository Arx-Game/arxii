"""Thread-weaving acquisition layer.

ThreadWeavingUnlock is the authored catalog of "you can weave threads on X"
unlocks. CharacterThreadWeavingUnlock is the per-character purchase record.
ThreadWeavingTeachingOffer is the teacher-facing offer, mirroring
CodexTeachingOffer.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.constants import TargetKind


class ThreadWeavingUnlock(SharedMemoryModel):
    """Authored unlock catalog. Discriminator + typed-FK; one unlock per anchor.

    No name/description: ``display_name`` derives from the discriminator FK
    (Spec A §2.1 lines 348-369). Per-kind partial UniqueConstraints +
    CheckConstraints enforce 'one unlock per anchor' and 'exactly one
    target_* set, matching target_kind' at the DB layer. ``clean()`` mirrors
    the same shape rules at the application layer.

    Spec A §2.1 lines 313-429.
    """

    target_kind = models.CharField(
        max_length=32,
        choices=TargetKind.choices,
        help_text="Discriminator selecting which unlock_* field is populated.",
    )

    unlock_trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="thread_weaving_unlocks",
        help_text="Set when target_kind=TRAIT; null otherwise.",
    )
    unlock_gift = models.ForeignKey(
        "magic.Gift",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="thread_weaving_unlocks",
        help_text="Set when target_kind=TECHNIQUE; covers all techniques under Gift.",
    )
    unlock_room_property = models.ForeignKey(
        "mechanics.Property",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="thread_weaving_unlocks",
        help_text="Set when target_kind=ROOM; rooms with this Property.",
    )
    unlock_track = models.ForeignKey(
        "relationships.RelationshipTrack",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="thread_weaving_unlocks",
        help_text="Set when target_kind=RELATIONSHIP_TRACK; per-track unlock.",
    )

    xp_cost = models.PositiveIntegerField(
        help_text="Base XP cost; multiplied by out_of_path_multiplier when out-of-Path.",
    )
    paths = models.ManyToManyField(
        "classes.Path",
        related_name="thread_weaving_unlocks",
        blank=True,
        help_text="Paths that treat this unlock as in-band (full xp_cost).",
    )
    out_of_path_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("2.0"),
        help_text="Cost multiplier applied when buyer's Path is not in `paths`.",
    )

    class Meta:
        constraints = [
            # ---- Per-kind partial UniqueConstraints (one per TargetKind, no CAPSTONE) -
            models.UniqueConstraint(
                fields=["unlock_trait"],
                condition=models.Q(target_kind="TRAIT"),
                name="unique_threadweaving_unlock_trait",
            ),
            models.UniqueConstraint(
                fields=["unlock_gift"],
                condition=models.Q(target_kind="TECHNIQUE"),
                name="unique_threadweaving_unlock_gift",
            ),
            models.UniqueConstraint(
                fields=["unlock_room_property"],
                condition=models.Q(target_kind="ROOM"),
                name="unique_threadweaving_unlock_room",
            ),
            models.UniqueConstraint(
                fields=["unlock_track"],
                condition=models.Q(target_kind="RELATIONSHIP_TRACK"),
                name="unique_threadweaving_unlock_track",
            ),
            # ---- Per-kind CheckConstraints (exactly one target_* set, others null) ----
            models.CheckConstraint(
                name="threadweaving_trait_payload",
                check=(
                    ~models.Q(target_kind="TRAIT")
                    | (
                        models.Q(unlock_trait__isnull=False)
                        & models.Q(unlock_gift__isnull=True)
                        & models.Q(unlock_room_property__isnull=True)
                        & models.Q(unlock_track__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="threadweaving_technique_payload",
                check=(
                    ~models.Q(target_kind="TECHNIQUE")
                    | (
                        models.Q(unlock_trait__isnull=True)
                        & models.Q(unlock_gift__isnull=False)
                        & models.Q(unlock_room_property__isnull=True)
                        & models.Q(unlock_track__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="threadweaving_room_payload",
                check=(
                    ~models.Q(target_kind="ROOM")
                    | (
                        models.Q(unlock_trait__isnull=True)
                        & models.Q(unlock_gift__isnull=True)
                        & models.Q(unlock_room_property__isnull=False)
                        & models.Q(unlock_track__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="threadweaving_track_payload",
                check=(
                    ~models.Q(target_kind="RELATIONSHIP_TRACK")
                    | (
                        models.Q(unlock_trait__isnull=True)
                        & models.Q(unlock_gift__isnull=True)
                        & models.Q(unlock_room_property__isnull=True)
                        & models.Q(unlock_track__isnull=False)
                    )
                ),
            ),
            # CAPSTONE has no slot on this model — capstones inherit from their
            # parent RELATIONSHIP_TRACK unlock per spec line 426. The 5
            # per-kind checks above all early-out for non-matching target_kind
            # values, so without this guard a CAPSTONE row with all target_*
            # slots empty would satisfy every check. Forbid it explicitly.
            models.CheckConstraint(
                name="threadweaving_no_capstone",
                check=~models.Q(target_kind="RELATIONSHIP_CAPSTONE"),
            ),
        ]

    # Field-name constants used by clean() / _get_target_value() to dispatch by
    # target_kind. Extracted so the STRING_LITERAL linter doesn't flag bare
    # string field names — and so renaming a target_* field forces a single
    # update here.
    _F_TRAIT = "unlock_trait"
    _F_GIFT = "unlock_gift"
    _F_ROOM = "unlock_room_property"
    _F_TRACK = "unlock_track"

    # Discriminator -> required field name. CAPSTONE is intentionally absent
    # (capstones inherit from RELATIONSHIP_TRACK unlocks per spec line 426).
    _KIND_TO_FIELD: dict[str, str] = {
        TargetKind.TRAIT: _F_TRAIT,
        TargetKind.TECHNIQUE: _F_GIFT,
        TargetKind.ROOM: _F_ROOM,
        TargetKind.RELATIONSHIP_TRACK: _F_TRACK,
    }
    _ALL_TARGET_FIELDS: tuple[str, ...] = (
        _F_TRAIT,
        _F_GIFT,
        _F_ROOM,
        _F_TRACK,
    )

    def _get_target_value(self, field_name: str) -> object | None:
        """Return the populated value for ``field_name``."""
        return getattr(self, field_name)

    @property
    def display_name(self) -> str:
        if self.target_kind == TargetKind.TRAIT:
            return f"ThreadWeaving: {self.unlock_trait.name}"
        if self.target_kind == TargetKind.TECHNIQUE:
            return f"ThreadWeaving: Gift of {self.unlock_gift.name}"
        if self.target_kind == TargetKind.ROOM:
            return f"ThreadWeaving: {self.unlock_room_property.name} spaces"
        if self.target_kind == TargetKind.RELATIONSHIP_TRACK:
            return f"ThreadWeaving: {self.unlock_track.name} bonds"
        return "ThreadWeaving: <unknown>"  # defensive; unreachable while choices apply

    def __str__(self) -> str:
        return self.display_name

    def clean(self) -> None:
        """Validate exactly-one-target rule.

        DB CheckConstraints catch the same shape errors at write time;
        clean() is the user-facing error path (forms / serializers / tests
        calling full_clean()).
        """
        expected_field = self._KIND_TO_FIELD.get(self.target_kind)
        if expected_field is None:
            raise ValidationError(
                {"target_kind": f"Unknown target_kind: {self.target_kind!r}."},
            )

        if self._get_target_value(expected_field) is None:
            raise ValidationError(
                {expected_field: f"target_kind={self.target_kind} requires {expected_field}."},
            )

        for field_name in self._ALL_TARGET_FIELDS:
            if field_name == expected_field:
                continue
            if self._get_target_value(field_name) is not None:
                raise ValidationError(
                    {
                        field_name: (
                            f"target_kind={self.target_kind} requires {field_name} to be empty."
                        ),
                    },
                )


class CharacterThreadWeavingUnlock(SharedMemoryModel):
    """Per-character purchase record for a ThreadWeavingUnlock.

    One row per (character, unlock) — enforced by unique_together. Records the
    actual XP paid (which depends on the buyer's Path: in-band uses ``xp_cost``,
    out-of-band multiplies by ``out_of_path_multiplier``) and optionally the
    teacher who unlocked it. Spec A §2.1 lines 431-440.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="thread_weaving_unlocks",
        help_text="Character who owns this purchase.",
    )
    unlock = models.ForeignKey(
        ThreadWeavingUnlock,
        on_delete=models.PROTECT,
        related_name="character_purchases",
        help_text="Authored unlock the character purchased.",
    )
    acquired_at = models.DateTimeField(auto_now_add=True)
    xp_spent = models.PositiveIntegerField(
        help_text="Actual XP paid (in-Path: xp_cost; out-of-Path: xp_cost * multiplier).",
    )
    teacher = models.ForeignKey(
        "roster.RosterTenure",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="thread_weaving_unlocks_taught",
        help_text="Teacher RosterTenure when applicable; audit only.",
    )

    class Meta:
        unique_together = (("character", "unlock"),)

    def __str__(self) -> str:
        return f"CharacterThreadWeavingUnlock<{self.character_id} -> {self.unlock_id}>"


class ThreadWeavingTeachingOffer(SharedMemoryModel):
    """Teacher-side offer linking a RosterTenure to a ThreadWeavingUnlock.

    Mirrors the existing CodexTeachingOffer model exactly. NPC academy teachers
    are seeded as RosterTenure-backed offers tied to specific ThreadWeaving
    unlocks. Path multiplier (in-band vs. out-of-band) is computed at acceptance
    time, not stored on the offer. Spec A §4.2 lines 1186-1198.
    """

    teacher = models.ForeignKey(
        "roster.RosterTenure",
        on_delete=models.CASCADE,
        related_name="thread_weaving_offers",
        help_text="Teaching tenure offering this unlock.",
    )
    unlock = models.ForeignKey(
        ThreadWeavingUnlock,
        on_delete=models.PROTECT,
        related_name="teaching_offers",
        help_text="Authored unlock being offered.",
    )
    pitch = models.TextField(
        help_text="Teacher's narrative pitch for this offer.",
    )
    gold_cost = models.PositiveIntegerField(
        default=0,
        help_text="Gold price the teacher charges (XP cost stays on the unlock).",
    )
    banked_ap = models.PositiveIntegerField(
        help_text="Teacher's AP commitment backing this offer.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"ThreadWeavingTeachingOffer<{self.teacher_id} -> {self.unlock_id}>"
