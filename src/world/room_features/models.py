"""Models for the Room Features framework.

Subsystem E of Plan 4. Provides the reusable install/upgrade machinery
that Sanctum (and future Library, Training Room, Lab, etc.) plug into.
Per-kind state lives in the feature's home-app details model (e.g.,
:class:`world.magic.models.sanctum.SanctumDetails`), keyed by OneToOne
back to :class:`RoomFeatureInstance`.
"""

from __future__ import annotations

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, UniqueConstraint
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from core.descriptors import ReverseOneToOneOrNone
from core.mixins import DiscriminatorMixin
from world.locations.constants import HolderType
from world.room_features.constants import (
    BRIG_CAPACITY_PER_LEVEL,
    VAULT_MAX_ITEMS_PER_LEVEL,
    DefenseKind,
    RoomFeatureInstallMechanism,
    RoomFeatureOwnerType,
    RoomFeatureServiceStrategy,
)

ROOM_PROFILE_MODEL = "evennia_extensions.RoomProfile"
_PERSONA_MODEL = "scenes.Persona"


class RoomFeatureKind(SharedMemoryModel):
    """Catalog row for a kind of installable room feature.

    Open catalog — staff-authorable. Plan 4 ships exactly one row
    (Sanctum) via :func:`world.room_features.seeds.ensure_sanctum_kind`.
    Other kinds (Library, Training Room, Lab, …) land via #675 content
    authoring without touching this model.

    Each row pairs a ``service_strategy`` key (selecting the per-kind
    install/upgrade handler from
    :mod:`world.room_features.services`) with the catalog metadata the
    install UI needs to filter and present choices.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(
        blank=True,
        help_text="Admin-editable flavor describing what this feature is.",
    )
    max_level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        help_text=(
            "Cap on the feature's level. Per-kind: Sanctum=5, Library might be 10, "
            "Training Room might be 3. Bounds ``RoomFeatureInstance.level`` and "
            "the install/upgrade wizard's target-level picker."
        ),
    )
    service_strategy = models.CharField(
        max_length=32,
        choices=RoomFeatureServiceStrategy.choices,
        unique=True,
        help_text=(
            "Key into the service-strategy registry. Each row's strategy is "
            "registered by the kind's home app at app-ready time. "
            "Unique — one kind per strategy."
        ),
    )
    allowed_building_kinds = models.ManyToManyField(
        "buildings.BuildingKind",
        blank=True,
        related_name="installable_features",
        help_text=(
            "Restrict installation to buildings of these kinds. Empty m2m "
            "means any building kind is allowed."
        ),
    )
    install_mechanism = models.CharField(
        max_length=10,
        choices=RoomFeatureInstallMechanism.choices,
        default=RoomFeatureInstallMechanism.PROJECT,
        help_text=(
            "How a level-1 install of this kind is triggered. Magical features "
            "(Sanctum, Wardstone, …) use RITUAL; physical features (Granary, "
            "Cannon Deck, …) use PROJECT. Upgrades (L1→L2+) are always Project-"
            "driven regardless. Plan 4 §E."
        ),
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(max_level__gte=1),
                name="room_feature_kind_max_level_gte_1",
            ),
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class RoomFeatureKindInstallRitual(SharedMemoryModel):
    """Per-(kind, variant) install ritual row for ``install_mechanism=RITUAL`` kinds.

    A single feature kind can advertise multiple install ritual variants:
    Sanctum has two — Ritual of Thine Own Sanctum (Personal) and Ritual of
    Blood Covenant Sanctification (Covenant). Future kinds with a single
    install ritual ship with one row and an empty ``variant_label``.
    """

    feature_kind = models.ForeignKey(
        RoomFeatureKind,
        on_delete=models.CASCADE,
        related_name="install_rituals",
    )
    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.PROTECT,
        related_name="installs_room_features",
    )
    variant_label = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text=(
            "Disambiguation label when a kind has multiple install ritual "
            "variants (Sanctum: 'Personal' / 'Covenant'). Empty for kinds "
            "with one install ritual."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["feature_kind", "ritual"],
                name="room_feature_kind_install_ritual_unique",
            ),
        ]
        ordering = ["feature_kind", "variant_label"]

    def __str__(self) -> str:
        label = f" ({self.variant_label})" if self.variant_label else ""
        return f"{self.feature_kind.name} ← {self.ritual_id}{label}"


class RoomFeatureKindOwnerType(SharedMemoryModel):
    """Allowed owner-type rows for a ``RoomFeatureKind``.

    Sanctum requires ``PERSONA`` OR ``ORG_COVENANT`` — two rows.
    Future "Heraldic Hall" might require only ``ORG_NOBLE``. Empty set
    (zero rows) means the kind imposes no owner-type restriction; the
    seed-side discipline is to author at least one row per kind that
    actually restricts ownership.
    """

    feature_kind = models.ForeignKey(
        RoomFeatureKind,
        on_delete=models.CASCADE,
        related_name="required_building_owner_types",
    )
    owner_type = models.CharField(
        max_length=20,
        choices=RoomFeatureOwnerType.choices,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["feature_kind", "owner_type"],
                name="room_feature_kind_owner_type_unique",
            ),
        ]
        ordering = ["feature_kind", "owner_type"]

    def __str__(self) -> str:
        return f"{self.feature_kind.name} allows {self.get_owner_type_display()}"


class RoomFeatureInstanceQuerySet(models.QuerySet):
    """Custom queryset for RoomFeatureInstance with soft-delete helpers."""

    def active(self) -> RoomFeatureInstanceQuerySet:
        """Return only instances where dissolved_at IS NULL (i.e. not dissolved)."""
        return self.filter(dissolved_at__isnull=True)


class RoomFeatureInstance(SharedMemoryModel):
    """A feature installed in one specific room.

    OneToOne with ``RoomProfile`` enforces the **one-feature-per-room**
    rule at the schema level. Per-kind state (Sanctum's resonance_type
    etc.) lives in a details model keyed by OneToOne back to this row.

    ``dissolved_at`` is set when the feature is dissolved; null means active.
    Dissolution is a soft-delete — the row and all story-significant data are
    preserved. Use ``.active()`` on the queryset to exclude dissolved instances.
    """

    # Reverse-OneToOne safe accessor (#2386): missing row -> None.
    field_details_or_none = ReverseOneToOneOrNone("field_details")

    # Reverse-OneToOne safe accessor (#2386): missing row -> None.
    sanctum_details_or_none = ReverseOneToOneOrNone("sanctum_details")

    room_profile = models.OneToOneField(
        ROOM_PROFILE_MODEL,
        on_delete=models.CASCADE,
        related_name="feature_instance",
        primary_key=True,
        help_text="The room this feature is installed in (one feature per room).",
    )
    feature_kind = models.ForeignKey(
        RoomFeatureKind,
        on_delete=models.PROTECT,
        related_name="instances",
    )
    level = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Current level. Bounded by ``feature_kind.max_level`` at write time.",
    )
    installed_at = models.DateTimeField(default=timezone.now)
    last_upgraded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set on each successful upgrade past level 1; null at install.",
    )
    dissolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the feature is dissolved; null = active.",
    )

    objects = RoomFeatureInstanceQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(level__gte=1),
                name="room_feature_instance_level_gte_1",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.feature_kind.name} L{self.level} @ room {self.room_profile_id}"


class RoomFeatureProgressionDetails(SharedMemoryModel):
    """Per-(ROOM_FEATURE_PROGRESSION Project) details payload.

    Created when an install/upgrade Project spawns; consumed by
    :func:`world.room_features.services.complete_room_feature_progression`
    when the project resolves. Mirrors Plan 3's
    ``BuildingConstructionDetails`` shape.
    """

    project = models.OneToOneField(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="room_feature_progression_details",
        primary_key=True,
    )
    target_room_profile = models.ForeignKey(
        ROOM_PROFILE_MODEL,
        on_delete=models.PROTECT,
        related_name="feature_progression_projects",
        help_text="The room the feature will be installed in or upgraded.",
    )
    target_feature_kind = models.ForeignKey(
        RoomFeatureKind,
        on_delete=models.PROTECT,
        related_name="progression_projects",
    )
    target_level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        help_text=(
            "The level this project aims to reach. Install → 1; upgrade → "
            "current+1 (or higher). Bounded by ``feature_kind.max_level`` at "
            "project-creation time."
        ),
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(target_level__gte=1),
                name="room_feature_progression_target_level_gte_1",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Progression#{self.project_id}: {self.target_feature_kind.name} L{self.target_level}"
        )


class Trap(SharedMemoryModel):
    """A room-anchored hazard resolved through the shared check / pool path.

    On entry an armed trap the entrant has not yet resolved runs a detection
    check (``detect_check_type``) whose graded outcome selects from
    ``consequence_pool``: a success tier carries no damage consequence (the
    entrant spots and avoids it), a failure tier fires the authored damage via
    the standard effect-handler path (``apply_resolution`` -> ``_deal_damage``
    -> ``process_damage_consequences``). ``disarm_check_type`` routes the same
    pool when a character actively disarms it. A room may hold several traps,
    so this is a plain FK (not the one-per-room OneToOne RoomFeatureInstance
    uses).
    """

    room_profile = models.ForeignKey(
        ROOM_PROFILE_MODEL,
        on_delete=models.CASCADE,
        related_name="traps",
        help_text="The room this trap is set in. A room may hold several traps.",
    )
    position = models.ForeignKey(
        "areas.Position",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="traps",
        help_text=(
            "Optional specific spot this hazard is anchored to. Unset (default) = "
            "room-wide, matching pre-#1317 behavior. When set, this trap only fires "
            "for a character actually occupying this Position — whether they walked "
            "there or were knocked there."
        ),
    )
    name = models.CharField(max_length=100)
    consequence_pool = models.ForeignKey(
        "actions.ConsequencePool",
        on_delete=models.PROTECT,
        related_name="traps",
        help_text=(
            "Graded damage payload, keyed by the detection/disarm check outcome "
            "tier: success tiers should carry no consequence (avoided); failure "
            "tiers deal the authored damage."
        ),
    )
    detect_check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        related_name="detect_traps",
        help_text="Check rolled on entry to spot the trap before it triggers.",
    )
    disarm_check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        related_name="disarm_traps",
        help_text="Check rolled by the disarm action.",
    )
    detect_difficulty = models.PositiveIntegerField(
        default=0,
        help_text="Authored target difficulty for the on-entry detection check.",
    )
    disarm_difficulty = models.PositiveIntegerField(
        default=0,
        help_text="Authored target difficulty for the disarm check.",
    )
    is_armed = models.BooleanField(
        default=True,
        help_text="A disarmed trap never triggers and cannot be disarmed again.",
    )
    is_hidden = models.BooleanField(
        default=True,
        help_text="Whether the trap is concealed until a character resolves it.",
    )
    detected_by = models.ManyToManyField(
        "character_sheets.CharacterSheet",
        related_name="detected_traps",
        blank=True,
        help_text=(
            "Characters for whom this trap is resolved — they spotted or already "
            "triggered it, so it neither re-triggers nor stays hidden for them."
        ),
    )

    # === Zone hazard lifecycle (#2019) ===
    duration_rounds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "For zone hazards: rounds until the hazard dissipates. "
            "Null = permanent trap (one-shot entry trigger)."
        ),
    )
    created_by_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conjured_hazards",
        help_text=(
            "Provenance: the caster who conjured this hazard. Null for staff-authored traps."
        ),
    )

    class Meta:
        ordering = ["room_profile_id", "name"]

    def __str__(self) -> str:
        state = "armed" if self.is_armed else "disarmed"
        return f"Trap '{self.name}' ({state}) @ room {self.room_profile_id}"


class PreparedGround(SharedMemoryModel):
    """A room a character has prepared as their battleground ahead of time (#2646).

    Design intent: "the fight was won yesterday" — a character who scouted, warded,
    or otherwise readied a room before combat ever breaks out there gets to have
    fought smart, not just hard. Recorded off an out-of-combat PERCEPTION-tagged
    technique cast (see ``world.covenants.perks.services.
    record_ground_preparation_from_cast``) by a character whose engaged covenant
    role carries ``CovenantRole.prepares_ground=True``.

    One active prepared ground per character (``prepared_by`` is a OneToOne) — the
    domain rule is deliberately last-writes-wins: re-preparing a different room
    MOVES the character's prepared ground there rather than stacking a second row.
    Consumed by ``world.combat.chosen_ground.compute_on_chosen_ground``, which
    stamps ``CombatEncounter.on_chosen_ground`` at encounter-creation time whenever
    the encounter's room holds a ``PreparedGround`` whose preparer is physically
    present.
    """

    room_profile = models.ForeignKey(
        ROOM_PROFILE_MODEL,
        on_delete=models.CASCADE,
        related_name="prepared_grounds",
        help_text="The room this ground was prepared in.",
    )
    prepared_by = models.OneToOneField(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="prepared_ground",
        help_text=(
            "The character who prepared this ground. One active prepared ground "
            "per character — re-preparing elsewhere moves this row rather than "
            "creating a second one."
        ),
    )
    prepared_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-prepared_at"]

    def __str__(self) -> str:
        return f"{self.prepared_by} prepared room {self.room_profile_id}"


class VaultDetails(SharedMemoryModel):
    """Per-(VAULT RoomFeatureInstance) details payload (#2179).

    Created when a vault install Project resolves (L1). OneToOne back to
    RoomFeatureInstance — the install/upgrade flow lives in
    world.room_features; the per-kind state lives here.

    The vault marks the room itself as a secure store. All unheld items
    in the room (items with no holder_character_sheet) are
    vault-protected: take is gated by the vault's access list,
    steal bypasses with the existing consent-gated theft machinery.
    """

    feature_instance = models.OneToOneField(
        "room_features.RoomFeatureInstance",
        on_delete=models.CASCADE,
        related_name="vault_details",
        primary_key=True,
    )
    founder_persona = models.ForeignKey(
        _PERSONA_MODEL,
        on_delete=models.PROTECT,
        related_name="founded_vaults",
        help_text=(
            "The persona who installed the vault. Has implicit owner "
            "access — always on the access list regardless of "
            "VaultAccessEntry rows. The founder's RosterTenure is the "
            "consent source for steal_permitted when an unowned vault "
            "item is stolen."
        ),
    )
    max_items = models.PositiveSmallIntegerField(
        default=VAULT_MAX_ITEMS_PER_LEVEL,
        help_text=(
            "Maximum loose items the vault room can hold. Scaled by "
            "level at install: max_items = level * "
            "VAULT_MAX_ITEMS_PER_LEVEL."
        ),
    )

    def __str__(self) -> str:
        return (
            f"Vault L{self.feature_instance.level} @ room {self.feature_instance.room_profile_id}"
        )


class VaultAccessEntry(DiscriminatorMixin, SharedMemoryModel):
    """A granted access right to a specific vault (#2179).

    The vault owner adds entries for personas or organizations.
    Organization entries grant access to all current members (any rank),
    mirroring LocationTenancy's org-membership composition.
    """

    DISCRIMINATOR_FIELD = "holder_type"
    DISCRIMINATOR_MAP = {
        HolderType.PERSONA: "holder_persona",
        HolderType.ORGANIZATION: "holder_organization",
    }

    vault_details = models.ForeignKey(
        VaultDetails,
        on_delete=models.CASCADE,
        related_name="access_entries",
    )
    holder_type = models.CharField(
        max_length=20,
        choices=HolderType.choices,
    )
    holder_persona = models.ForeignKey(
        _PERSONA_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="vault_access_entries",
    )
    holder_organization = models.ForeignKey(
        "societies.Organization",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="vault_access_entries",
    )
    added_by = models.ForeignKey(
        _PERSONA_MODEL,
        on_delete=models.PROTECT,
        related_name="vault_access_granted",
    )
    added_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["vault_details", "holder_persona"],
                condition=Q(holder_type="PERSONA"),
                name="vault_access_persona_unique",
            ),
            UniqueConstraint(
                fields=["vault_details", "holder_organization"],
                condition=Q(holder_type="ORGANIZATION"),
                name="vault_access_org_unique",
            ),
        ]
        ordering = ["vault_details", "added_at"]

    def __str__(self) -> str:
        target = self.get_active_target_name()
        return f"Vault access: {target} ({self.holder_type})"


class DefenseDetailsQuerySet(models.QuerySet):
    """Shared soft-delete queryset for the three #2177 defense-details models."""

    def active(self) -> DefenseDetailsQuerySet:
        return self.filter(dissolved_at__isnull=True)


class ExitBarsDetails(SharedMemoryModel):
    """Bars installed on one specific exit (#2177).

    OneToOne with ExitProfile -- independent of RoomFeatureInstance (which is
    one-per-room, not one-per-exit) and of any other exit from the same room.
    `level` scales durability; BreakExitAction (#2176) drops it by 1 per
    successful break, dissolving the row at 0 rather than flooring it.
    """

    exit_profile = models.OneToOneField(
        "evennia_extensions.ExitProfile",
        on_delete=models.CASCADE,
        related_name="bars_details",
        primary_key=True,
        help_text="The exit these bars are installed on.",
    )
    level = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Durability tier. Capped at EXIT_BARS_MAX_LEVEL.",
    )
    installed_at = models.DateTimeField(default=timezone.now)
    last_upgraded_at = models.DateTimeField(null=True, blank=True)
    dissolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the bars are broken to destruction; null = active.",
    )

    objects = DefenseDetailsQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(level__gte=1),
                name="exit_bars_details_level_gte_1",
            ),
        ]

    def __str__(self) -> str:
        return f"Bars L{self.level} @ exit {self.exit_profile_id}"


class RoomWardDetails(SharedMemoryModel):
    """A magical ward installed on a room (#2177).

    OneToOne with RoomProfile -- independent of RoomFeatureInstance (a room
    may hold a LAB/SANCTUM AND a ward simultaneously). Reaction is
    deterministic (no CheckType roll, Decision 5): apply `reaction_condition`
    and/or deal `reaction_damage_amount` to an unauthorized entrant.
    `resonance_reserve` is drained daily by `room_ward_upkeep_tick`;
    depletion sets `lapsed_at` (the ward stops reacting but is never
    dissolved by lapsing alone).
    """

    room_profile = models.OneToOneField(
        ROOM_PROFILE_MODEL,
        on_delete=models.CASCADE,
        related_name="ward_details",
        primary_key=True,
        help_text="The room this ward protects.",
    )
    level = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Ward tier. Capped at ROOM_WARD_MAX_LEVEL.",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="wards",
        help_text="The resonance flavor powering this ward's upkeep.",
    )
    resonance_reserve = models.PositiveIntegerField(
        default=0,
        help_text="Banked resonance the daily upkeep tick drains from.",
    )
    reaction_condition = models.ForeignKey(
        "conditions.ConditionTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ward_reactions",
        help_text="Condition applied to an unauthorized entrant, if set.",
    )
    reaction_damage_amount = models.PositiveIntegerField(
        default=0,
        help_text="Damage dealt to an unauthorized entrant, if nonzero.",
    )
    installed_at = models.DateTimeField(default=timezone.now)
    last_upgraded_at = models.DateTimeField(null=True, blank=True)
    lapsed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when resonance_reserve hits 0; ward stops reacting. Null = active.",
    )
    dissolved_at = models.DateTimeField(null=True, blank=True)

    objects = DefenseDetailsQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(level__gte=1),
                name="room_ward_details_level_gte_1",
            ),
        ]

    def __str__(self) -> str:
        return f"Ward L{self.level} @ room {self.room_profile_id}"


class RoomAlarmDetails(SharedMemoryModel):
    """An alarm installed on a room (#2177).

    OneToOne with RoomProfile -- independent of RoomFeatureInstance and of
    RoomWardDetails (a room may hold both simultaneously). On an unauthorized
    entry, echoes to the room (identity-transparent, ADR-0083) and notifies
    the room's owner and/or tenant personas via send_narrative_message
    (offline-safe -- covers tenant-only rooms, e.g. a new character's
    starting residence, which have no LocationOwnership row). No resonance
    upkeep -- only the ward is magical.
    """

    room_profile = models.OneToOneField(
        ROOM_PROFILE_MODEL,
        on_delete=models.CASCADE,
        related_name="alarm_details",
        primary_key=True,
        help_text="The room this alarm watches.",
    )
    level = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Alarm tier. Capped at ROOM_ALARM_MAX_LEVEL.",
    )
    installed_at = models.DateTimeField(default=timezone.now)
    last_upgraded_at = models.DateTimeField(null=True, blank=True)
    dissolved_at = models.DateTimeField(null=True, blank=True)

    objects = DefenseDetailsQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(level__gte=1),
                name="room_alarm_details_level_gte_1",
            ),
        ]

    def __str__(self) -> str:
        return f"Alarm L{self.level} @ room {self.room_profile_id}"


class DefenseProgressionDetails(SharedMemoryModel):
    """Per-(ROOM_DEFENSE_INSTALLATION Project) details payload (#2177).

    Mirrors RoomFeatureProgressionDetails' shape but targets the independent
    defense-details models instead of RoomFeatureKind/RoomFeatureInstance.
    Exactly one of target_exit_profile/target_room_profile is set, matching
    defense_kind (enforced by the CheckConstraint below).
    """

    project = models.OneToOneField(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="defense_progression_details",
        primary_key=True,
    )
    defense_kind = models.CharField(max_length=16, choices=DefenseKind.choices)
    target_exit_profile = models.ForeignKey(
        "evennia_extensions.ExitProfile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="defense_progression_projects",
        help_text="Set only for EXIT_BARS installs/upgrades.",
    )
    target_room_profile = models.ForeignKey(
        ROOM_PROFILE_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="defense_progression_projects",
        help_text="Set only for ROOM_WARD/ROOM_ALARM installs/upgrades.",
    )
    target_level = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="defense_progression_projects",
        help_text="Required for ROOM_WARD installs only.",
    )
    reaction_condition = models.ForeignKey(
        "conditions.ConditionTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="defense_progression_projects",
        help_text=(
            "Optional ward reaction condition (ROOM_WARD installs only). "
            "Must be from a ConditionCategory with is_negative=True."
        ),
    )
    reaction_damage_amount = models.PositiveIntegerField(
        default=0,
        null=True,
        blank=True,
        help_text="Optional ward reaction damage (ROOM_WARD installs only).",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(target_level__gte=1),
                name="defense_progression_target_level_gte_1",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(
                        defense_kind=DefenseKind.EXIT_BARS,
                        target_exit_profile__isnull=False,
                        target_room_profile__isnull=True,
                    )
                    | models.Q(
                        defense_kind__in=[DefenseKind.ROOM_WARD, DefenseKind.ROOM_ALARM],
                        target_exit_profile__isnull=True,
                        target_room_profile__isnull=False,
                    )
                ),
                name="defense_progression_target_matches_kind",
            ),
        ]

    def __str__(self) -> str:
        return f"DefenseProgression#{self.project_id}: {self.defense_kind} L{self.target_level}"


class BrigDetails(SharedMemoryModel):
    """Per-(BRIG RoomFeatureInstance) details payload (#1862).

    Created when a brig install Project resolves (L1). OneToOne back to
    RoomFeatureInstance — the install/upgrade flow lives in
    world.room_features; the per-kind state lives here.

    The brig marks the room as a holding cell for captured characters.
    Capacity scales by level: max_prisoners = level * BRIG_CAPACITY_PER_LEVEL.
    """

    feature_instance = models.OneToOneField(
        "room_features.RoomFeatureInstance",
        on_delete=models.CASCADE,
        related_name="brig_details",
        primary_key=True,
    )
    max_prisoners = models.PositiveSmallIntegerField(
        default=BRIG_CAPACITY_PER_LEVEL,
        help_text=(
            "Maximum captives the brig can hold. Scaled by level at install:"
            " max_prisoners = level * BRIG_CAPACITY_PER_LEVEL."
        ),
    )

    def __str__(self) -> str:
        return f"Brig L{self.feature_instance.level} @ room {self.feature_instance.room_profile_id}"
