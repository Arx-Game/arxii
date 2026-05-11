"""Multi-participant ritual session coordination models.

See `docs/superpowers/specs/2026-05-10-covenants-slice-b-design.md` §4.2-§4.4
for full design rationale.
"""

from __future__ import annotations

from django.db import models
from django.db.models import CheckConstraint, Q, UniqueConstraint
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from world.character_sheets.models import CharacterSheet
from world.covenants.models import Covenant, CovenantRole
from world.magic.constants import ParticipantState, ReferenceKind
from world.magic.models.rituals import Ritual


class RitualSession(SharedMemoryModel):
    """Transient coordination row for a multi-participant ritual.

    Persists only during PENDING / READY. Deleted on fire/cancel/expiry/
    threshold-killing decline. Audit trail lives on the resulting domain rows.
    """

    ritual = models.ForeignKey(Ritual, on_delete=models.PROTECT)
    initiator = models.ForeignKey(CharacterSheet, on_delete=models.PROTECT)
    proposed_terms = models.TextField(blank=True)
    session_kwargs = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    @cached_property
    def participants_cached(self) -> list:
        """Prefetch target for participants via Prefetch(to_attr='participants_cached')."""
        return list(self.participants.all())

    @cached_property
    def references_cached(self) -> list:
        """Prefetch target for references via Prefetch(to_attr='references_cached')."""
        return list(self.references.all())


class RitualSessionParticipant(SharedMemoryModel):
    session = models.ForeignKey(
        RitualSession,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    character_sheet = models.ForeignKey(CharacterSheet, on_delete=models.PROTECT)
    state = models.CharField(
        max_length=16,
        choices=ParticipantState.choices,
        default=ParticipantState.INVITED,
    )
    participant_kwargs = models.JSONField(default=dict, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["session", "character_sheet"],
                name="ritual_session_participant_unique_per_session",
            ),
        ]


class RitualSessionReference(SharedMemoryModel):
    session = models.ForeignKey(
        RitualSession,
        on_delete=models.CASCADE,
        related_name="references",
    )
    participant = models.ForeignKey(
        RitualSessionParticipant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="references",
    )
    kind = models.CharField(max_length=32, choices=ReferenceKind.choices)
    ref_covenant = models.ForeignKey(
        Covenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ritualsessionreference_set",
    )
    ref_covenant_role = models.ForeignKey(
        CovenantRole,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ritualsessionreference_set",
    )

    class Meta:
        constraints = [
            CheckConstraint(
                check=(
                    (
                        Q(kind=ReferenceKind.COVENANT)
                        & Q(ref_covenant__isnull=False)
                        & Q(ref_covenant_role__isnull=True)
                    )
                    | (
                        Q(kind=ReferenceKind.COVENANT_ROLE)
                        & Q(ref_covenant__isnull=True)
                        & Q(ref_covenant_role__isnull=False)
                    )
                ),
                name="ritual_session_reference_exactly_one_ref",
            ),
        ]
