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
        max_length=32,
        choices=GainSource.choices,
        help_text="Discriminator. Identifies which source_* FK is populated.",
    )
    granted_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Typed source FKs — exactly one non-null per row, matching ``source``.
    source_room_profile = models.ForeignKey(
        "evennia_extensions.RoomProfile",
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
    outfit_item_facet = models.ForeignKey(
        "items.ItemFacet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resonance_grants",
        help_text="Set when source=OUTFIT_TRICKLE; the ItemFacet that produced this trickle.",
    )
    source_sanctum_details = models.ForeignKey(
        "magic.SanctumDetails",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resonance_grants",
        help_text=(
            "Set when source in (SANCTUM_WEAVING, SANCTUM_OWNER_BONUS); the "
            "Sanctum whose cron tick paid this grant. Plan 4 §F."
        ),
    )
    source_project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resonance_grants",
        help_text=(
            "Set when source=PROJECT_CONTRIBUTION; the Project whose "
            "resolution paid this contributor's grant. Plan 1+."
        ),
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
            # ROOM_RESIDENCE: exactly source_room_profile populated, others null.
            models.CheckConstraint(
                name="res_grant_residence_shape",
                check=(
                    Q(source="ROOM_RESIDENCE")
                    & Q(source_room_profile__isnull=False)
                    & Q(source_staff_account__isnull=True)
                    & Q(source_pose_endorsement__isnull=True)
                    & Q(source_scene_entry_endorsement__isnull=True)
                    & Q(outfit_item_facet__isnull=True)
                    & Q(source_sanctum_details__isnull=True)
                    & Q(source_project__isnull=True)
                )
                | ~Q(source="ROOM_RESIDENCE"),
            ),
            # STAFF_GRANT: room_profile null, pose_endorsement null, scene_entry null
            # (staff_account remains nullable by design — retirement can null it)
            models.CheckConstraint(
                name="res_grant_staff_shape",
                check=(
                    Q(source="STAFF_GRANT")
                    & Q(source_room_profile__isnull=True)
                    & Q(source_pose_endorsement__isnull=True)
                    & Q(source_scene_entry_endorsement__isnull=True)
                    & Q(outfit_item_facet__isnull=True)
                    & Q(source_sanctum_details__isnull=True)
                    & Q(source_project__isnull=True)
                )
                | ~Q(source="STAFF_GRANT"),
            ),
            # POSE_ENDORSEMENT: exactly pose_endorsement populated, others null
            models.CheckConstraint(
                name="res_grant_pose_endorsement_shape",
                check=(
                    Q(source="POSE_ENDORSEMENT")
                    & Q(source_pose_endorsement__isnull=False)
                    & Q(source_room_profile__isnull=True)
                    & Q(source_staff_account__isnull=True)
                    & Q(source_scene_entry_endorsement__isnull=True)
                    & Q(outfit_item_facet__isnull=True)
                    & Q(source_sanctum_details__isnull=True)
                    & Q(source_project__isnull=True)
                )
                | ~Q(source="POSE_ENDORSEMENT"),
            ),
            # SCENE_ENTRY: exactly scene_entry_endorsement populated, others null
            models.CheckConstraint(
                name="res_grant_scene_entry_shape",
                check=(
                    Q(source="SCENE_ENTRY")
                    & Q(source_scene_entry_endorsement__isnull=False)
                    & Q(source_room_profile__isnull=True)
                    & Q(source_staff_account__isnull=True)
                    & Q(source_pose_endorsement__isnull=True)
                    & Q(outfit_item_facet__isnull=True)
                    & Q(source_sanctum_details__isnull=True)
                    & Q(source_project__isnull=True)
                )
                | ~Q(source="SCENE_ENTRY"),
            ),
            # OUTFIT_TRICKLE: exactly outfit_item_facet populated, other source FKs null
            models.CheckConstraint(
                name="res_grant_outfit_trickle_shape",
                check=(
                    Q(source="OUTFIT_TRICKLE")
                    & Q(outfit_item_facet__isnull=False)
                    & Q(source_room_profile__isnull=True)
                    & Q(source_staff_account__isnull=True)
                    & Q(source_pose_endorsement__isnull=True)
                    & Q(source_scene_entry_endorsement__isnull=True)
                    & Q(source_sanctum_details__isnull=True)
                    & Q(source_project__isnull=True)
                )
                | ~Q(source="OUTFIT_TRICKLE"),
            ),
            # SANCTUM_WEAVING (Plan 4 §F): no other source FK is set.
            # source_sanctum_details is set at creation by grant_resonance's
            # service-level validation (_SOURCE_REQUIRED_KWARG) but allowed
            # to NULL post-Dissolution via on_delete=SET_NULL — keeping the
            # constraint NOT-NULL would brick Dissolution at commit time.
            models.CheckConstraint(
                name="res_grant_sanctum_weaving_shape",
                check=(
                    Q(source="SANCTUM_WEAVING")
                    & Q(source_room_profile__isnull=True)
                    & Q(source_staff_account__isnull=True)
                    & Q(source_pose_endorsement__isnull=True)
                    & Q(source_scene_entry_endorsement__isnull=True)
                    & Q(outfit_item_facet__isnull=True)
                    & Q(source_project__isnull=True)
                )
                | ~Q(source="SANCTUM_WEAVING"),
            ),
            # SANCTUM_OWNER_BONUS (Plan 4 §F): same pattern as SANCTUM_WEAVING.
            models.CheckConstraint(
                name="res_grant_sanctum_owner_bonus_shape",
                check=(
                    Q(source="SANCTUM_OWNER_BONUS")
                    & Q(source_room_profile__isnull=True)
                    & Q(source_staff_account__isnull=True)
                    & Q(source_pose_endorsement__isnull=True)
                    & Q(source_scene_entry_endorsement__isnull=True)
                    & Q(outfit_item_facet__isnull=True)
                    & Q(source_project__isnull=True)
                )
                | ~Q(source="SANCTUM_OWNER_BONUS"),
            ),
            # SANCTUM_DISSOLUTION_RECOVERY (Plan 4 §F revised 2026-06-03):
            # source_sanctum_details set at grant creation, then nulled when
            # the Sanctum's row is dissolved later in the same transaction.
            models.CheckConstraint(
                name="res_grant_sanctum_dissolution_recovery_shape",
                check=(
                    Q(source="SANCTUM_DISSOLUTION_RECOVERY")
                    & Q(source_room_profile__isnull=True)
                    & Q(source_staff_account__isnull=True)
                    & Q(source_pose_endorsement__isnull=True)
                    & Q(source_scene_entry_endorsement__isnull=True)
                    & Q(outfit_item_facet__isnull=True)
                    & Q(source_project__isnull=True)
                )
                | ~Q(source="SANCTUM_DISSOLUTION_RECOVERY"),
            ),
            # PROJECT_CONTRIBUTION (Plan 1+): exactly source_project populated
            models.CheckConstraint(
                name="res_grant_project_contribution_shape",
                check=(
                    Q(source="PROJECT_CONTRIBUTION")
                    & Q(source_project__isnull=False)
                    & Q(source_room_profile__isnull=True)
                    & Q(source_staff_account__isnull=True)
                    & Q(source_pose_endorsement__isnull=True)
                    & Q(source_scene_entry_endorsement__isnull=True)
                    & Q(outfit_item_facet__isnull=True)
                    & Q(source_sanctum_details__isnull=True)
                )
                | ~Q(source="PROJECT_CONTRIBUTION"),
            ),
        ]

    def __str__(self) -> str:
        return f"ResonanceGrant({self.amount} {self.resonance_id} via {self.source})"
