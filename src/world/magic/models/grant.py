"""ResonanceGrant — universal audit ledger for gain events (Spec C §2.4).

Discriminator + typed-FK pattern matching Spec A's Thread model. Each row
identifies exactly one typed source FK matching the ``source`` discriminator.
CheckConstraints enforce the shape at the DB level.

The pose_endorsement / scene_entry_endorsement / item_instance typed source
FKs are added in later tasks (Task 13, Task 17, and future Items ship)
once their referenced models exist.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.constants import GainSource


class ResonanceGrant(SharedMemoryModel):
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="resonance_grants",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
    )
    amount = models.PositiveIntegerField()
    source = models.CharField(
        max_length=24,
        choices=GainSource.choices,
        help_text="Discriminator. Identifies which source_* FK is populated.",
    )
    granted_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Typed source FKs — exactly one non-null per row, matching ``source``.
    # (pose / scene-entry FKs added in Tasks 13 / 17.)
    source_room_aura_profile = models.ForeignKey(
        "magic.RoomAuraProfile",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="resonance_grants",
    )
    source_staff_account = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resonance_grants_issued",
    )
    source_pose_endorsement = models.ForeignKey(
        "magic.PoseEndorsement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="resonance_grants",
    )
    source_scene_entry_endorsement = models.ForeignKey(
        "magic.SceneEntryEndorsement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="resonance_grants",
    )

    class Meta:
        indexes = [
            models.Index(
                fields=["character_sheet", "granted_at"],
                name="res_grant_sheet_time_idx",
            ),
            models.Index(
                fields=["character_sheet", "source", "granted_at"],
                name="res_grant_sheet_source_idx",
            ),
        ]
        constraints = [
            # ROOM_RESIDENCE: exactly room_aura_profile populated, others null
            models.CheckConstraint(
                name="res_grant_residence_shape",
                check=(
                    Q(source="ROOM_RESIDENCE")
                    & Q(source_room_aura_profile__isnull=False)
                    & Q(source_staff_account__isnull=True)
                    & Q(source_pose_endorsement__isnull=True)
                    & Q(source_scene_entry_endorsement__isnull=True)
                )
                | ~Q(source="ROOM_RESIDENCE"),
            ),
            # STAFF_GRANT: room_aura_profile null, pose_endorsement null, scene_entry null
            # (staff_account remains nullable by design — retirement can null it)
            models.CheckConstraint(
                name="res_grant_staff_shape",
                check=(
                    Q(source="STAFF_GRANT")
                    & Q(source_room_aura_profile__isnull=True)
                    & Q(source_pose_endorsement__isnull=True)
                    & Q(source_scene_entry_endorsement__isnull=True)
                )
                | ~Q(source="STAFF_GRANT"),
            ),
            # POSE_ENDORSEMENT: exactly pose_endorsement populated, others null
            models.CheckConstraint(
                name="res_grant_pose_endorsement_shape",
                check=(
                    Q(source="POSE_ENDORSEMENT")
                    & Q(source_pose_endorsement__isnull=False)
                    & Q(source_room_aura_profile__isnull=True)
                    & Q(source_staff_account__isnull=True)
                    & Q(source_scene_entry_endorsement__isnull=True)
                )
                | ~Q(source="POSE_ENDORSEMENT"),
            ),
            # SCENE_ENTRY: exactly scene_entry_endorsement populated, others null
            models.CheckConstraint(
                name="res_grant_scene_entry_shape",
                check=(
                    Q(source="SCENE_ENTRY")
                    & Q(source_scene_entry_endorsement__isnull=False)
                    & Q(source_room_aura_profile__isnull=True)
                    & Q(source_staff_account__isnull=True)
                    & Q(source_pose_endorsement__isnull=True)
                )
                | ~Q(source="SCENE_ENTRY"),
            ),
        ]

    def __str__(self) -> str:
        return f"ResonanceGrant({self.amount} {self.resonance_id} via {self.source})"
