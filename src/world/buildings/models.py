"""Building system models.

Per the Plan 3 spec (#668):

- ``BuildingKind`` is an open catalog (rows, not enum) with non-exclusive
  descriptive boolean flags.
- ``BuildingSizeTier`` (#670) maps ``target_size`` to a total space budget;
  rooms spend their ``RoomSizeTier`` units from it (no flat room cap).
- ``Building`` decorates an ``Area`` at level BUILDING; spawned by
  ``BUILDING_CONSTRUCTION`` Project completion.
- ``BuildingMaterial`` is the per-Building snapshot of materials used
  during construction — survives the source ItemInstance (which is
  consumed) and drives ``Building.computed_stats()``.
- ``MaterialLoreEffect`` attaches per-template special properties to
  building stats (godswar stone → resonance amp, etc.). Plan 3 ships the
  model with zero rows; content authoring populates it.
- ``BuildingPermitDetails`` is the per-instance details for a permit
  ItemInstance. Persona-scoped (per the IC vs OOC ownership tenet); will
  collapse into ``ItemInstance.holder_persona`` once #684 lands.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.buildings import room_constants
from world.buildings.constants import ConditionTier
from world.locations.constants import StatKey

# Cross-app FK string constants. Django resolves these lazily at app-ready
# time; centralizing them here avoids the "literal duplicated N times" SonarCloud
# code smell and gives a single grep target if the source model ever moves.
_BUILDING_MODEL_PATH = "buildings.Building"
_PROJECT_FK = "projects.Project"
_POLISH_CATEGORY_FK = "buildings.PolishCategory"
_PERSONA_FK = "scenes.Persona"
_CODEX_SUBJECT_FK = "codex.CodexSubject"
_ARCHITECTURAL_STYLE_FK = "buildings.ArchitecturalStyle"
_ROOM_PROFILE_FK = "evennia_extensions.RoomProfile"


class BuildingKind(NaturalKeyMixin, SharedMemoryModel):
    """An authorable category of building.

    Open catalog — rows authored by staff, not an enum. Each row carries
    non-exclusive descriptive flags (a fortified floating witch-king
    manor is ``residential + fortified + occult + aerial``).

    Per the brainstorm, the flag set is NOT a taxonomy. Flags are
    sort/filter axes used by authoring NPCs to decide what they issue
    permits for. Multiple flags can be true on one row.

    Carries `NaturalKeyMixin` (#2266 review fix) so the content pipeline's
    emitted fixture JSON (natural-key format, no "pk" key) resolves an
    existing same-name row on `loaddata` instead of blind-INSERTing into it
    and raising `IntegrityError` on the unique `name` constraint. Per #946,
    `loaddata` on a `SharedMemoryModel` can INSERT via a natural key but
    cannot UPDATE — the identity map returns the cached instance before the
    new field values land. `core_management.content_fixtures.load_entries`
    (`update_or_create`) remains the only update-safe path; the emitted
    fixture JSON is fresh-DB/insert-or-resolve only.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(
        blank=True,
        help_text="Admin-editable flavor describing what this kind is.",
    )
    # Non-exclusive descriptive flags — see Plan 3 spec.
    is_residential = models.BooleanField(default=False)
    is_commercial = models.BooleanField(default=False)
    is_fortified = models.BooleanField(default=False)
    is_occult = models.BooleanField(default=False)
    is_maritime = models.BooleanField(default=False)
    is_agrarian = models.BooleanField(default=False)
    is_aerial = models.BooleanField(default=False)
    is_subterranean = models.BooleanField(default=False)
    is_secret = models.BooleanField(default=False)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class PropertyGrantProfile(NaturalKeyMixin, SharedMemoryModel):
    """A reusable catalog row configuring "grant a persona an already-existing Building".

    Not tied to any specific beginning, ward, or game concept — that's
    content, wired via ``Beginnings.property_grant_profile`` or any future
    caller of ``grant_property_house``. A profile with ``activation_target_tier``
    unset grants an already-active building at ``initial_condition_tier``
    (e.g. a livable dormitory chamber); one with it set grants an
    upkeep-exempt building that needs a ``BUILDING_ACTIVATION`` project to
    reach that tier (e.g. a ruin needing a first-time civic rite).
    """

    name = models.CharField(max_length=100, unique=True)
    building_kind = models.ForeignKey(
        BuildingKind,
        on_delete=models.PROTECT,
        related_name="property_grant_profiles",
    )
    ward_area = models.ForeignKey(
        "areas.Area",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="property_grant_profiles",
        help_text=(
            "Parent Area new grants are placed under. NULL falls back to a "
            "shared placeholder Ward Area, lazily created — real content "
            "sets this via fixture upsert with no code change."
        ),
    )
    initial_condition_tier = models.PositiveSmallIntegerField(
        choices=ConditionTier.choices,
        default=ConditionTier.DECAYED,
        help_text="Condition tier the Building starts at when granted.",
    )
    activation_target_tier = models.PositiveSmallIntegerField(
        choices=ConditionTier.choices,
        null=True,
        blank=True,
        help_text=(
            "NULL: the grant is already active at initial_condition_tier — "
            "no activation arc, no upkeep exemption. Set: the granted "
            "Building starts upkeep-exempt and requires a BUILDING_ACTIVATION "
            "project to reach this tier."
        ),
    )
    activation_cost_floor_coppers = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Flat coppers-per-target_size floor for the activation project's "
            "funding threshold. Only consulted when activation_target_tier is set."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class BuildingSizeTier(SharedMemoryModel):
    """Named building size → total space budget (#670; PLACEHOLDER magnitudes).

    ``Building.target_size`` indexes into this table at construction to
    snapshot ``space_budget``. Super-linear by design (ratified on #670):
    one big build ≈ 2× the budget of two half-size builds — a
    consolidation premium. Admin-editable rows; the economy pass retunes
    values without code changes.
    """

    tier = models.PositiveSmallIntegerField(unique=True)
    name = models.CharField(max_length=40, unique=True)
    space_budget = models.PositiveIntegerField()

    class Meta:
        ordering = ["tier"]

    def __str__(self) -> str:
        return f"{self.name} (tier {self.tier}, {self.space_budget} units)"


class MaterialLoreEffect(SharedMemoryModel):
    """Per-template lore effect applied when a material is used in construction.

    Plan 3 ships this model with **zero rows**. Content authoring fills
    it in over time — godswar stone gets a row giving resonance_amp,
    Primeval Lumber gets one giving fey_attunement, etc.

    Effect semantics: for every ``units_per_tier`` units of this template
    used in a building's materials, the building gains
    ``magnitude_per_tier`` of ``target_stat``. Capped at
    ``max_tiers`` × magnitude (null = uncapped).
    """

    template = models.ForeignKey(
        "items.ItemTemplate",
        on_delete=models.CASCADE,
        related_name="lore_effects",
    )
    target_stat = models.CharField(
        max_length=64,
        help_text=(
            "Which building stat is affected. Open vocabulary — consumer "
            "systems (sanctum, defense, prestige) define which stats they "
            "read. ``Building.computed_stats()`` aggregates whatever is "
            "set here without interpretation."
        ),
    )
    units_per_tier = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text=(
            "Every N units of this material grants one tier of magnitude. "
            "Must be >= 1; zero would divide-by-zero in computed_stats()."
        ),
    )
    magnitude_per_tier = models.IntegerField(
        help_text="Magnitude granted per tier (can be negative).",
    )
    max_tiers = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Cap on tiers from this material. Null = uncapped.",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(units_per_tier__gte=1),
                name="material_lore_effect_units_per_tier_gte_1",
            ),
        ]

    def __str__(self) -> str:
        cap = "" if self.max_tiers is None else f", cap {self.max_tiers}"
        return (
            f"{self.template_id}: +{self.magnitude_per_tier} {self.target_stat} "
            f"per {self.units_per_tier} units{cap}"
        )


class Building(SharedMemoryModel):
    """A construction result — decorates an ``Area`` at level BUILDING.

    Spawned by ``complete_building_construction`` when a
    ``BUILDING_CONSTRUCTION`` project completes. Composition over
    inheritance: Building has OneToOne to Area rather than subclassing
    via Django MTI, which keeps Area clean and avoids the MTI overhead.
    """

    area = models.OneToOneField(
        "areas.Area",
        on_delete=models.CASCADE,
        related_name="building_profile",
        primary_key=True,
        help_text="The Area row this Building decorates. Must be level BUILDING.",
    )
    # #676 Phase D: owner_persona credits Building polish into
    # prestige_from_dwellings on the owner. Nullable for newly-constructed
    # buildings that haven't been formally deeded yet (intermediate state
    # the existing construction flow doesn't otherwise distinguish).
    owner_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_buildings",
        help_text=(
            "Persona credited for this building's polish (Renown system). "
            "Building polish flows into owner.prestige_from_dwellings. "
            "Room polish also rolls up to this persona (intentional "
            "double-count when same persona owns building + tenants a room)."
        ),
    )
    # #1930 — condition-tier ladder. Nonpayment slides this (arrears first,
    # bounded floor); it NEVER mutates polish/feature rows. The tier
    # step-modulates the owner's prestige_from_dwellings.
    condition_tier = models.PositiveSmallIntegerField(
        choices=ConditionTier.choices,
        default=ConditionTier.EXCELLENT,
        help_text=(
            "Condition ladder position (#1930). EXCELLENT is the normal "
            "state held by ordinary paid upkeep; above-normal tiers come "
            "from preparation and decay on a dwell timer; below-normal "
            "tiers come from sustained missed upkeep, floored at DECAYED."
        ),
    )
    condition_since = models.DateTimeField(
        default=timezone.now,
        help_text=(
            "When condition_tier last changed. Drives the above-normal "
            "dwell decay (ABOVE_NORMAL_DWELL_DAYS)."
        ),
    )
    upkeep_arrears = models.PositiveBigIntegerField(
        default=0,
        help_text=(
            "Owed upkeep in coppers, accrued on missed weeks and capped at "
            "ARREARS_CAP_WEEKS × weekly cost. Owner-only surface; settled "
            "via settle_upkeep_arrears."
        ),
    )
    ultra_upkeep = models.BooleanField(
        default=False,
        help_text=(
            "Owner opt-in premium (ULTRA_UPKEEP_MULTIPLIER × weekly cost, "
            "on top of normal upkeep) that holds IMMACULATE past its dwell."
        ),
    )
    mothballed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Set when long owner inactivity hides this building from the "
            "grid and freezes all upkeep/condition accrual (#1930). "
            "Cleared when the owner returns."
        ),
    )
    consecutive_missed_upkeep = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Consecutive missed weekly upkeep cycles for this building "
            "(building-scoped; upkeep is charged per building). Past "
            "GRACE_MISSES the condition tier slides every "
            "SLIP_WEEKS_PER_TIER further misses."
        ),
    )
    consecutive_paid_upkeep = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Consecutive paid weekly cycles — every REGAIN_WEEKS_PER_TIER "
            "paid weeks climbs one tier back toward EXCELLENT."
        ),
    )
    kind = models.ForeignKey(
        BuildingKind,
        on_delete=models.PROTECT,
        related_name="buildings",
    )
    architectural_style = models.ForeignKey(
        _ARCHITECTURAL_STYLE_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="buildings",
        help_text=(
            "Architectural style (#1514) — orthogonal to kind. Its StyleAffinity rows are "
            "materialized as climate modifiers on this building's Area (cascading to its rooms) "
            "via buildings.services.set_building_style. Changing it is a renovation Project."
        ),
    )
    target_size = models.PositiveSmallIntegerField(
        help_text=(
            "Construction-time size target (1-10). Snapshotted from the "
            "Project at completion. Mutable via BUILDING_UPGRADE (#673)."
        ),
    )
    target_grandeur = models.PositiveSmallIntegerField(
        help_text=(
            "Construction-time grandeur target (1-10). Snapshotted from the Project at completion."
        ),
    )
    space_budget = models.PositiveIntegerField(
        help_text=(
            "Total room-size units this building can hold (#670). Snapshotted at "
            "construction from BuildingSizeTier[target_size]; raised by "
            "BUILDING_EXTENSION. Rooms spend their RoomSizeTier units from this pool."
        ),
    )
    fortification_level = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Persistent defense investment (#1713), raised via a FORTIFICATION_UPGRADE "
            "Project (see world.buildings.fortification_services). Snapshotted into a "
            "battle Fortification's max_integrity when one is created against this "
            "Building — see world.battles.services.create_fortification. Capped at "
            "MAX_FORTIFICATION_LEVEL (world.buildings.room_constants)."
        ),
    )
    entry_room = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="entry_for_buildings",
        help_text=(
            "The building's designated entrance (#670): fallback destination for "
            "evicted contents/characters and the root of exit-connectivity checks. "
            "Undroppable; otherwise an ordinary room."
        ),
    )
    constructed_at = models.DateTimeField(auto_now_add=True)
    constructed_by_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="buildings_constructed",
    )
    source_project = models.OneToOneField(
        _PROJECT_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resulting_building",
        help_text=(
            "The BUILDING_CONSTRUCTION project that produced this Building. "
            "OneToOne so re-running ``complete_building_construction`` on a "
            "completed project hits the unique constraint and the in-Python "
            "idempotency guard catches the duplicate first."
        ),
    )
    granted_via_profile = models.ForeignKey(
        "buildings.PropertyGrantProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_buildings",
        help_text=(
            "Provenance: the PropertyGrantProfile that produced this Building, "
            "if granted rather than constructed via a permit."
        ),
    )
    property_granted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "When this Building was granted via grant_property_house. "
            "NULL for constructed buildings."
        ),
    )
    property_activated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "When this granted Building reached its profile's activation_target_tier "
            "(stamped immediately at grant if the profile has no activation arc). "
            "NULL while property_granted_at is set means upkeep-exempt and "
            "refurbish-refused."
        ),
    )

    def __str__(self) -> str:
        return f"{self.kind.name}: {self.area.name}"

    def delete(self, *args: object, **kwargs: object) -> tuple[int, dict[str, int]]:
        """Delete Building AND its decorated Area together.

        Building.area is the primary key (OneToOne) — deleting Area
        cascades to Building, but deleting Building directly would leave
        the Area orphaned (a level=BUILDING Area with no decorator).
        Override delete() to remove both atomically so callers can't
        accidentally strand an Area.
        """
        area = self.area
        result = super().delete(*args, **kwargs)
        # Now delete the Area — cascade-deletes ownership/tenancy rows.
        area.delete()
        return result

    def computed_stats(self) -> dict[str, int]:
        """Aggregate per-stat magnitudes from material lore effects.

        Walks ``materials_used``, looks up ``MaterialLoreEffect`` rows
        per material template, sums ``min(tiers, max_tiers) × magnitude_per_tier``
        per target_stat. Returns ``{stat_name: total_magnitude}``.

        **Callers MUST prefetch** to avoid N+1::

            Building.objects.prefetch_related(
                "materials_used__item_template__lore_effects"
            )

        Without that prefetch, a Building with N materials × M effects
        triggers N×M queries. Plan 3 ships this method as the framework
        hook; with no ``MaterialLoreEffect`` rows authored yet, it
        returns an empty dict. Content authoring populates the effect
        rows; downstream systems (sanctum, defense, prestige) interpret
        the stat names.
        """
        stats: dict[str, int] = {}
        for material in self.materials_used.all():
            for effect in material.item_template.lore_effects.all():
                tiers = material.units // effect.units_per_tier
                if effect.max_tiers is not None:
                    tiers = min(tiers, effect.max_tiers)
                if tiers <= 0:
                    continue
                stats[effect.target_stat] = (
                    stats.get(effect.target_stat, 0) + tiers * effect.magnitude_per_tier
                )
        return stats


class BuildingMaterial(SharedMemoryModel):
    """Per-Building snapshot of a material contribution at construction.

    Survives the source ItemInstance (consumed at project completion).
    ``Building.computed_stats()`` reads these rows + the
    ``MaterialLoreEffect`` rows on the template to derive runtime
    building statistics.
    """

    building = models.ForeignKey(
        Building,
        on_delete=models.CASCADE,
        related_name="materials_used",
    )
    item_template = models.ForeignKey(
        "items.ItemTemplate",
        on_delete=models.PROTECT,
        related_name="building_uses",
    )
    item_instance_pk = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Original ``ItemInstance.pk`` for audit. The instance itself "
            "is deleted at project completion; this is the soft record."
        ),
    )
    units = models.PositiveIntegerField(default=1)
    quality_tier = models.ForeignKey(
        "items.QualityTier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    lore_value = models.IntegerField(
        default=0,
        help_text="Snapshotted ``ItemInstance.lore_value`` at contribution time.",
    )
    contributed_by_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="materials_contributed",
    )
    contributed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.building}: {self.units}× {self.item_template_id}"


class BuildingPermitDetails(SharedMemoryModel):
    """Per-(BuildingPermit ItemInstance) details for a building permit.

    A permit is a consumable ``ItemInstance`` of the seeded BuildingPermit
    template. This decorator carries the IC-meaningful state:

    - ``holder_persona`` — the IC owner; persona-scoped so different
      personas of the same account don't share permits. Frozen at
      issuance. Will collapse into ``ItemInstance.holder_persona``
      once #684 lands.
    - ``building_kind`` — what kind of building this permit authorizes
    - ``approved_wards`` — where the permit is valid
    - ``max_target_size`` — cap on the construction size target

    Mirrors the ``ItemFacet`` composition pattern (OneToOne to
    ItemInstance) rather than per-kind inheritance.
    """

    item_instance = models.OneToOneField(
        "items.ItemInstance",
        on_delete=models.CASCADE,
        related_name="building_permit_details",
        primary_key=True,
    )
    # #684: dropped ``holder_persona`` — ownership now lives on
    # ``ItemInstance.holder_character_sheet`` (the body). ``holder_persona_name``
    # below is preserved as the issuance-time IC-name snapshot for audit; the
    # live persona is derived at render time from the holder sheet's primary
    # persona (or ``ItemInstance.crafter_persona_display`` if set at issuance).
    holder_persona_name = models.CharField(
        max_length=200,
        blank=True,
        help_text=(
            "Snapshot of holder_persona's display name at issuance — "
            "preserves the audit trail when the persona is later deleted."
        ),
    )
    building_kind = models.ForeignKey(
        BuildingKind,
        on_delete=models.PROTECT,
        related_name="permits",
    )
    approved_wards = models.ManyToManyField(
        "areas.Area",
        related_name="building_permits_valid_in",
        blank=True,
        help_text=(
            "Wards (Areas at level WARD) where this permit can be activated. "
            "Snapshotted at issuance."
        ),
    )
    max_target_size = models.PositiveSmallIntegerField(
        default=10,
        help_text="Cap on the construction project's ``target_size``.",
    )
    cost_modifier = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        default=Decimal("1.000"),
        help_text="Multiplier on construction-side costs negotiated at issuance.",
    )
    issued_by_role = models.ForeignKey(
        "npc_services.NPCRole",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="permits_issued",
        help_text="The NPC role that issued this permit (audit).",
    )
    issued_at = models.DateTimeField(auto_now_add=True)
    notes_text = models.TextField(
        blank=True,
        help_text="IC flavor of how the permit was negotiated.",
    )
    consumed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the permit was activated and consumed by a construction project.",
    )
    consumed_by_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="permits_consumed",
        help_text=(
            "Persona that activated the permit. Expected to equal "
            "``holder_persona``; recorded separately for audit."
        ),
    )

    # #684: dropped the (holder_persona, *) index + (holder_persona,
    # issued_by_role) one-unconsumed-per-holder constraint along with the
    # field. The dedupe-defence migrates to a per-holder-sheet constraint
    # once #684 lands its companion BuildingPermitDetails follow-up; until
    # then the in-flow OfferCooldown gate prevents the front-end
    # double-click that motivated the original guard.

    def __str__(self) -> str:
        used = "consumed" if self.consumed_at else "unconsumed"
        return (
            f"BuildingPermit#{self.pk} ({self.building_kind}, {used}, "
            f"holder={self.holder_persona_name or '<deleted>'})"
        )


class BuildingExtensionDetails(SharedMemoryModel):
    """Per-(BUILDING_EXTENSION Project) details payload (#670).

    Growing a building's ``space_budget`` is a funded project (money /
    materials / AP through the standard contribution pipe); rooms dug
    *within* the budget are instant and free. ``applied_at`` is the
    idempotency marker — the handler adds the budget exactly once.
    """

    project = models.OneToOneField(
        _PROJECT_FK,
        on_delete=models.CASCADE,
        related_name="building_extension_details",
        primary_key=True,
    )
    building = models.ForeignKey(
        _BUILDING_MODEL_PATH,
        on_delete=models.CASCADE,
        related_name="extension_details",
    )
    added_budget = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Space-budget units this extension adds on completion.",
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the budget was applied; NULL until the handler runs. Idempotency marker.",
    )

    class Meta:
        verbose_name_plural = "Building extension details"

    def __str__(self) -> str:
        return f"Extension +{self.added_budget} units for building {self.building_id}"


class FortificationUpgradeDetails(SharedMemoryModel):
    """Per-(FORTIFICATION_UPGRADE Project) details payload (#1713).

    Mirrors BuildingExtensionDetails, but uses monotonic max-set semantics on
    completion (world.buildings.fortification_services.complete_fortification_upgrade)
    rather than an additive delta — target_level (not a delta) is the natural
    authoring unit for a level, and a naive overwrite could regress the level if a
    lower-target Project happens to complete after a higher one already did.
    """

    project = models.OneToOneField(
        _PROJECT_FK,
        on_delete=models.CASCADE,
        related_name="fortification_upgrade_details",
        primary_key=True,
    )
    building = models.ForeignKey(
        _BUILDING_MODEL_PATH,
        on_delete=models.CASCADE,
        related_name="fortification_upgrade_details",
    )
    target_level = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(room_constants.MAX_FORTIFICATION_LEVEL),
        ],
        help_text="Fortification level this upgrade targets on completion.",
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the level was applied; NULL until the handler runs. Idempotency marker.",
    )

    class Meta:
        verbose_name_plural = "Fortification upgrade details"

    def __str__(self) -> str:
        return f"Fortification upgrade -> level {self.target_level} for building {self.building_id}"


class BuildingRenovationDetails(SharedMemoryModel):
    """Per-(BUILDING_RENOVATION Project) details payload (#1858).

    Re-points an existing Building to a different admin-authored
    ``BuildingKind`` on completion, changing its descriptive flag set
    (e.g. a residential manor becomes an "Occult Manor"). Set-once semantics
    — mirrors ``FortificationUpgradeDetails``: the handler assigns
    ``Building.kind`` exactly once via the ``applied_at`` idempotency
    marker. Does not change ``target_size`` / ``space_budget`` (use
    ``BUILDING_EXTENSION`` / ``BUILDING_UPGRADE`` for those).

    See ``world/buildings/AGENT_GLOSSARY.md``: the nine boolean flags
    (``is_occult`` etc.) are catalog-level cosmetic/filter tags on
    ``BuildingKind``, not per-instance state — so a renovation swaps the
    catalog row rather than mutating flags on ``Building`` itself.
    """

    project = models.OneToOneField(
        _PROJECT_FK,
        on_delete=models.CASCADE,
        related_name="building_renovation_details",
        primary_key=True,
    )
    building = models.ForeignKey(
        _BUILDING_MODEL_PATH,
        on_delete=models.CASCADE,
        related_name="renovation_details",
    )
    target_kind = models.ForeignKey(
        "buildings.BuildingKind",
        on_delete=models.PROTECT,
        related_name="renovation_targets",
        help_text="The catalog BuildingKind this building is re-pointed to on completion.",
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the kind was re-pointed; NULL until the handler runs. Idempotency marker.",
    )

    class Meta:
        verbose_name_plural = "Building renovation details"

    def __str__(self) -> str:
        return f"Renovation -> kind {self.target_kind_id} for building {self.building_id}"


class BuildingActivationDetails(SharedMemoryModel):
    """Per-(BUILDING_ACTIVATION Project) details payload.

    Set-once semantics on completion (mirrors BuildingRenovationDetails):
    the handler sets Building.condition_tier to the snapshotted target_tier
    exactly once via the applied_at idempotency marker, and stamps
    Building.property_activated_at.
    """

    project = models.OneToOneField(
        _PROJECT_FK,
        on_delete=models.CASCADE,
        related_name="building_activation_details",
        primary_key=True,
    )
    building = models.ForeignKey(
        _BUILDING_MODEL_PATH,
        on_delete=models.CASCADE,
        related_name="activation_details",
    )
    target_tier = models.PositiveSmallIntegerField(
        choices=ConditionTier.choices,
        help_text="Snapshot of the granting profile's activation_target_tier at commission time.",
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When condition_tier was set; NULL until the handler runs. Idempotency marker.",
    )

    class Meta:
        verbose_name_plural = "Building activation details"

    def __str__(self) -> str:
        return f"Activation -> tier {self.target_tier} for building {self.building_id}"


class BuildingPreparationDetails(SharedMemoryModel):
    """Per-(BUILDING_PREPARATION Project) details payload (#1930).

    The cleanup/party-preparation loop: pushing a building one condition
    tier ABOVE Excellent is a small funded project — its threshold is a
    proportion of the house's base prestige (the shine you're buying),
    funded with coppers through the standard contribution pipe and sped
    along with AP Household Command checks (``ContributionMethod``). The
    handler climbs ``Building.condition_tier`` to ``target_tier`` exactly
    once via the ``applied_at`` idempotency marker, and only when the
    threshold was actually met (a lapsed, underfunded preparation fizzles).
    """

    project = models.OneToOneField(
        _PROJECT_FK,
        on_delete=models.CASCADE,
        related_name="building_preparation_details",
        primary_key=True,
    )
    building = models.ForeignKey(
        "buildings.Building",
        on_delete=models.CASCADE,
        related_name="preparation_details",
    )
    target_tier = models.PositiveSmallIntegerField(
        choices=ConditionTier.choices,
        help_text="Condition tier applied on completion (current tier + 1 at commission).",
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the tier was applied; NULL until the handler runs. Idempotency marker.",
    )

    class Meta:
        verbose_name_plural = "Building preparation details"

    def __str__(self) -> str:
        return f"Preparation -> tier {self.target_tier} for building {self.building_id}"


class BuildingUpgradeDetails(SharedMemoryModel):
    """Per-(BUILDING_UPGRADE Project) details payload (#1888).

    Bumps an existing Building's ``target_size`` up to a higher tier on
    completion and re-snapshots ``space_budget`` from the
    ``BuildingSizeTier`` table — e.g. upgrading a tier-3 House to a tier-4
    Manor grows the space budget from 250 to 600. Larger material/labor cost
    than ``BUILDING_EXTENSION``; prestige uplift. Does not change the
    building's ``kind`` (use ``BUILDING_RENOVATION`` for that).

    Monotonic max-set semantics on completion (mirrors
    ``FortificationUpgradeDetails``): the handler sets
    ``building.target_size = max(current, new_target_size)`` so a lower-target
    upgrade completing after a higher one doesn't regress the size.
    """

    project = models.OneToOneField(
        _PROJECT_FK,
        on_delete=models.CASCADE,
        related_name="building_upgrade_details",
        primary_key=True,
    )
    building = models.ForeignKey(
        _BUILDING_MODEL_PATH,
        on_delete=models.CASCADE,
        related_name="upgrade_details",
    )
    new_target_size = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(room_constants.MAX_BUILDING_SIZE_TIER),
        ],
        help_text="Size tier this upgrade targets on completion.",
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the size was applied; NULL until the handler runs. Idempotency marker.",
    )

    class Meta:
        verbose_name_plural = "Building upgrade details"

    def __str__(self) -> str:
        return f"Upgrade -> size {self.new_target_size} for building {self.building_id}"


class InteriorDesignDetails(SharedMemoryModel):
    """Per-(INTERIOR_DESIGN Project) details payload (#670).

    Commissions an admin-authored polish ``ProjectTemplate`` against a
    building (or one room of it, when ``room`` is set). On completion the
    handler finally drives the polish machinery: ``apply_project_completion``
    for building targets, per-increment ``apply_room_polish_delta`` for room
    targets.
    """

    project = models.OneToOneField(
        _PROJECT_FK,
        on_delete=models.CASCADE,
        related_name="interior_design_details",
        primary_key=True,
    )
    template = models.ForeignKey(
        "buildings.ProjectTemplate",
        on_delete=models.PROTECT,
        related_name="design_details",
    )
    building = models.ForeignKey(
        _BUILDING_MODEL_PATH,
        on_delete=models.CASCADE,
        related_name="design_details",
    )
    room = models.ForeignKey(
        _ROOM_PROFILE_FK,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="design_details",
        help_text="Target room; NULL = the whole building.",
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the polish was applied; NULL until the handler runs. Idempotency marker.",
    )

    class Meta:
        verbose_name_plural = "Interior design details"

    def __str__(self) -> str:
        target = f"room {self.room_id}" if self.room_id else f"building {self.building_id}"
        return f"Interior design '{self.template}' for {target}"


class BuildingConstructionDetails(SharedMemoryModel):
    """Per-(BUILDING_CONSTRUCTION Project) details payload.

    Plan 1 set up the Project framework with per-kind details models;
    this is the one for the BUILDING_CONSTRUCTION kind. Created when
    a permit is activated and the construction project spawns; consumed
    by ``complete_building_construction`` when the project completes.
    """

    project = models.OneToOneField(
        _PROJECT_FK,
        on_delete=models.CASCADE,
        related_name="building_construction_details",
        primary_key=True,
    )
    permit_details = models.ForeignKey(
        BuildingPermitDetails,
        on_delete=models.PROTECT,
        related_name="construction_projects",
        help_text="The (consumed) permit that authorized this construction.",
    )
    ward = models.ForeignKey(
        "areas.Area",
        on_delete=models.PROTECT,
        related_name="construction_projects",
        help_text="The ward this building will rise in.",
    )
    target_size = models.PositiveSmallIntegerField()
    target_grandeur = models.PositiveSmallIntegerField()
    constructed_by_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="construction_projects_led",
        help_text=(
            "Persona that initiated the construction. SET_NULL so persona "
            "deletion doesn't block the project's audit row. Audit ledger "
            "lives on OwnershipEvent.notes for full attribution."
        ),
    )

    def __str__(self) -> str:
        return (
            f"Construction#{self.project_id}: {self.permit_details.building_kind.name} "
            f"size={self.target_size} grandeur={self.target_grandeur}"
        )


# ---------------------------------------------------------------------------
# #676 Phase D — Dwellings polish system
#
# Polish accumulates on buildings + rooms via two paths:
#   * Projects — large additive chunks (50-10,000+) authored via
#     ProjectTemplate.polish_increments. Add at project-completion time.
#   * Items — small per-item contributions (0.1-1 typical, signature
#     items higher). Phase F adds the RoomItem placement model that
#     routes ItemTemplate.polish_value into RoomPolish.
#
# Polish is purely additive — no caps. Tier labels (Modest / Notable /
# Grand / Palatial …) are derived from TierThreshold rows per category,
# not stored on the buildings/rooms.
#
# Ownership credits (#670, home-anchored — replaces the #676 double-count):
#   * prestige_from_dwellings = the persona's PRIMARY-HOME room polish
#     (LocationTenancy.is_primary_home), plus the building's polish iff
#     the persona owns that building (Building.owner_persona).
# ---------------------------------------------------------------------------


class PolishCategory(SharedMemoryModel):
    """Admin-authored polish dimension (Opulence, Elegance, Provenance, …).

    Buildings and rooms accumulate polish along multiple independent
    categories. Tier labels are derived per-category via TierThreshold.
    The category name is the public-facing string.
    """

    name = models.CharField(max_length=60, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Polish categories"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class TierThreshold(SharedMemoryModel):
    """Admin-tunable label boundary for a polish category.

    Example: ``PolishCategory(Elegance)`` might have thresholds
    ``Modest@0``, ``Notable@500``, ``Grand@2500``, ``Palatial@10000``.
    A building with 3000 Elegance polish displays as "Grand in Elegance".
    """

    category = models.ForeignKey(
        PolishCategory,
        on_delete=models.CASCADE,
        related_name="tier_thresholds",
    )
    tier_name = models.CharField(max_length=60)
    min_value = models.PositiveIntegerField(
        validators=[MinValueValidator(0)],
        help_text="Minimum polish value at which this tier label applies.",
    )

    class Meta:
        ordering = ["category", "-min_value"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "tier_name"],
                name="buildings_polish_tier_unique_per_category",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.category.name}: {self.tier_name} @ {self.min_value}"


class BuildingPolish(SharedMemoryModel):
    """Per-(building, category) accumulated polish value.

    Through table; one row per (building, category). Created lazily by
    the polish-add service. Values are integers despite the spec's
    "0.1 per item" framing — internal storage uses scaled integers, with
    callers multiplying small per-item floats by 10 before storage so
    we never deal with floating-point polish totals.
    """

    building = models.ForeignKey(
        Building,
        on_delete=models.CASCADE,
        related_name="polish_by_category",
    )
    category = models.ForeignKey(
        PolishCategory,
        on_delete=models.CASCADE,
        related_name="building_polish_rows",
    )
    value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["building", "category"],
                name="buildings_polish_unique_per_category",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.building}: {self.value} {self.category.name}"


class RoomPolish(SharedMemoryModel):
    """Per-(room, category) accumulated polish value.

    Through table on RoomProfile (which extends ObjectDB and is the
    Django-side handle for Evennia rooms in this codebase). Same shape
    as BuildingPolish.
    """

    room = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        on_delete=models.CASCADE,
        related_name="polish_by_category",
    )
    category = models.ForeignKey(
        PolishCategory,
        on_delete=models.CASCADE,
        related_name="room_polish_rows",
    )
    value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room", "category"],
                name="buildings_room_polish_unique_per_category",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.room}: {self.value} {self.category.name}"


class ProjectTemplate(SharedMemoryModel):
    """Admin-authored template for a polish-adding project.

    A ProjectTemplate is the blueprint ("Gilded Walls", "Marble Foyer",
    "Tapestry of Origins") with admin-set polish increments per category,
    base cost, weekly upkeep, and decay priority. Commissioning a project
    instantiates the template into a Project (existing system) that
    resolves into a ``BuildingProjectInstance`` snapshot at completion.

    Tier prerequisites are M2M to TierThreshold — commissioning checks
    each tier prereq against the building's current polish-by-category.
    """

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    tier_prerequisites = models.ManyToManyField(
        TierThreshold,
        blank=True,
        related_name="gated_project_templates",
        help_text=(
            "Tier thresholds the target building must already meet before "
            "this template can be commissioned. Empty = no prereqs."
        ),
    )
    base_cost = models.PositiveIntegerField(
        default=0,
        help_text="Gold cost to commission this project (Phase E will wire deduction).",
    )
    weekly_upkeep_cost = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Coppers per real-time week to keep this project's polish "
            "active. The weekly cron sinks it from the owner's purse (#932)."
        ),
    )
    project_kind = models.CharField(
        max_length=40,
        blank=True,
        help_text=(
            "ProjectKind discriminator the underlying Project uses when "
            "this template is commissioned. Blank for templates that "
            "represent direct polish authoring (no Project lifecycle)."
        ),
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ProjectTemplatePolishIncrement(SharedMemoryModel):
    """Per-(template, category) polish increment row.

    Through table for ProjectTemplate.polish_increments. Lets a single
    template add to multiple categories with different values
    ("Marble Foyer": 800 Opulence + 200 Elegance).
    """

    template = models.ForeignKey(
        ProjectTemplate,
        on_delete=models.CASCADE,
        related_name="polish_increment_rows",
    )
    category = models.ForeignKey(
        PolishCategory,
        on_delete=models.CASCADE,
        related_name="polish_increment_rows",
    )
    value = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["template", "category"],
                name="buildings_polish_increment_unique_per_category",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.template.name}: +{self.value} {self.category.name}"


class BuildingProjectInstance(SharedMemoryModel):
    """Snapshot of a completed polish-adding project on a specific building.

    Created by ``apply_project_completion`` when a ProjectTemplate
    finishes on a building. Carries the polish per category plus the
    weekly upkeep contribution. The BuildingPolish row stores the
    building's total polish-by-category; instances store the per-feature
    contribution. Polish rows are never mutated by missed upkeep
    (#1930 — neglect slides Building.condition_tier instead); removal
    is rare (admin only).
    """

    building = models.ForeignKey(
        Building,
        on_delete=models.CASCADE,
        related_name="project_instances",
    )
    template = models.ForeignKey(
        ProjectTemplate,
        on_delete=models.PROTECT,
        related_name="instances",
    )
    source_project = models.OneToOneField(
        _PROJECT_FK,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resulting_building_project_instance",
        help_text=(
            "The completed Project that produced this instance. "
            "OneToOne so re-running apply_project_completion catches "
            "the duplicate at the unique constraint level."
        ),
    )
    weekly_upkeep_cost = models.PositiveIntegerField(
        default=0,
        help_text="Snapshotted from template at completion (admin-tunable on template).",
    )
    last_upkeep_paid_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last successful weekly upkeep deduction.",
    )

    class Meta:
        ordering = ["pk"]

    def __str__(self) -> str:
        return f"{self.template.name} on {self.building}"


class BuildingProjectInstancePolish(SharedMemoryModel):
    """Per-(instance, category) current polish value for this completed feature.

    Decays write to ``value`` here directly. The aggregate per-building
    per-category total in BuildingPolish is recomputed from the sum of
    these rows after every decay sweep (Phase E).
    """

    instance = models.ForeignKey(
        BuildingProjectInstance,
        on_delete=models.CASCADE,
        related_name="polish_by_category",
    )
    category = models.ForeignKey(
        PolishCategory,
        on_delete=models.CASCADE,
        related_name="instance_polish_rows",
    )
    value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["instance", "category"],
                name="buildings_instance_polish_unique_per_category",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.instance}: {self.value} {self.category.name}"


class ArchitecturalStyle(SharedMemoryModel):
    """An authorable architectural style for buildings (#1514).

    Orthogonal to ``BuildingKind`` (a Manor can be Shroudbound Gothic *or* Reefian). Carries
    climate (and, later, other) affinities as ``StyleAffinity`` rows. Its player-facing lore
    lives in the linked ``CodexSubject`` — knowing that subject is what lets a character build
    in the style, and the description is surfaced inline at point-of-use (the builder picker),
    not siloed in the Codex app.
    """

    name = models.CharField(max_length=100, unique=True)
    codex_subject = models.ForeignKey(
        _CODEX_SUBJECT_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="architectural_styles",
        help_text=(
            "Player-facing lore/description (discovery-gated). Knowing this subject gates "
            "buildability and supplies the builder's inline blurb. PLACEHOLDER prose seeded "
            "from the authored style lore."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this style can be selected for new builds.",
    )
    is_default = models.BooleanField(
        default=True,
        help_text=(
            "Default-available (living-realm tier). Non-default styles are the "
            "discoverable throwback tier (#1469): buildable only once the persona's "
            "character KNOWS an entry under codex_subject (research-unlocked)."
        ),
    )
    prestige_bonus = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Base dwelling-prestige addend for a building wearing this style "
            "(#1469 throwback tier). PLACEHOLDER magnitudes pending the tuning pass."
        ),
    )
    cost_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        default=1,
        help_text=(
            "Construction/renovation cost knob for this style (#1469). Data only for "
            "now — charging awaits the economy pass (Phase E cost deduction is unwired)."
        ),
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class StyleAffinity(SharedMemoryModel):
    """One modifier an architectural style imparts to its building's rooms (#1514).

    ``(style, stat_key) -> value``: positive = a vulnerability (an open-air style → +COLD,
    −HEAT), negative = insulation (thick stone → −COLD). Materialized as
    ``LocationValueModifier`` rows on the building's Area when a style is assigned (cascading to
    its rooms). Adding a new *kind* of mod later (defenses, …) is a new row on a new stat axis —
    data, not a migration. Magnitudes are a PLACEHOLDER author pass.
    """

    style = models.ForeignKey(
        ArchitecturalStyle,
        on_delete=models.CASCADE,
        related_name="affinities",
    )
    stat_key = models.CharField(max_length=20, choices=StatKey.choices)
    value = models.IntegerField(
        help_text="Modifier magnitude: + = vulnerability (more exposure), − = insulation.",
    )

    class Meta:
        ordering = ["style", "stat_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["style", "stat_key"], name="unique_style_affinity_per_axis"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.style.name}: {self.stat_key} {self.value:+d}"


class DecorationKind(NaturalKeyMixin, SharedMemoryModel):
    """A catalog decoration/furnishing that passively mods a room's comfort by presence (#1514).

    Lightweight + **stackable** — distinct from `RoomFeatureKind` (an *exclusive* capability you
    install as a Project). A decoration confers stats simply by being in the room. The fire/cold
    philosophy: a decoration mostly **cancels** discomfort on a specific axis (a hearth → −COLD,
    via `DecorationAffinity`) and adds only a **small** `amenity`; luxury pieces are mostly
    amenity. Placement is cosmetic/instant (owner-gated, money/material cost). Magnitudes are a
    PLACEHOLDER author pass.

    Carries `NaturalKeyMixin` (#2266 review fix) so the content pipeline's
    emitted fixture JSON (natural-key format, no "pk" key) resolves an
    existing same-name row on `loaddata` instead of blind-INSERTing into it
    and raising `IntegrityError` on the unique `name` constraint — the exact
    collision hit when content re-authors a decoration whose name a seeder
    (`ensure_decoration_kinds()`) already created (e.g. "Great Hearth"). Per
    #946, `loaddata` on a `SharedMemoryModel` can INSERT via a natural key
    but cannot UPDATE — the identity map returns the cached instance before
    the new field values land. `core_management.content_fixtures.load_entries`
    (`update_or_create`) remains the only update-safe path; the emitted
    fixture JSON is fresh-DB/insert-or-resolve only.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(
        blank=True,
        help_text="Admin-editable flavour describing the decoration. PLACEHOLDER.",
    )
    amenity = models.IntegerField(
        default=0,
        help_text=(
            "Positive comfort points (the AMENITY pool) added by presence. Small for utility "
            "pieces (a hearth is mostly mitigation); large for luxury/magical comfort."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class DecorationAffinity(SharedMemoryModel):
    """One discomfort-mitigation a decoration kind imparts (#1514): ``(kind, stat_key, value)``.

    Usually negative — it *cancels* that discomfort axis (hearth → COLD −N), floored at 0 by the
    axis clamp so it can never overcorrect into the opposite. Materialized as a room-scoped
    `LocationValueModifier` when the decoration is placed.
    """

    kind = models.ForeignKey(
        DecorationKind,
        on_delete=models.CASCADE,
        related_name="affinities",
    )
    stat_key = models.CharField(max_length=20, choices=StatKey.choices)
    value = models.IntegerField(
        help_text="Usually negative: mitigates that discomfort axis. + would add exposure.",
    )

    class Meta:
        ordering = ["kind", "stat_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "stat_key"], name="unique_decoration_affinity_per_axis"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind.name}: {self.stat_key} {self.value:+d}"


class RoomDecoration(SharedMemoryModel):
    """An instance of a decoration placed in a room (#1514). Stackable — many per room.

    Placing it materializes the kind's amenity + affinities as room-scoped
    `LocationValueModifier`s (source-tagged for clean removal); see
    `buildings.services.place_decoration` / `remove_decoration`.
    """

    room_profile = models.ForeignKey(
        _ROOM_PROFILE_FK,
        on_delete=models.CASCADE,
        related_name="decorations",
    )
    kind = models.ForeignKey(
        DecorationKind,
        on_delete=models.PROTECT,
        related_name="placements",
    )
    placed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["room_profile", "placed_at"]

    def __str__(self) -> str:
        return f"{self.kind.name} in room {self.room_profile_id}"


class MothballedRoomState(SharedMemoryModel):
    """Pre-mothball ``RoomProfile.is_public`` snapshot for one room (#1930).

    Written when long owner inactivity mothballs a building (rooms are
    hidden from public listings); read back — then deleted — when the
    owner returns, so mixed public/private room setups restore
    faithfully. FK lives here (buildings → evennia_extensions), keeping
    the RoomProfile primitive dependency-free (ADR-0010).
    """

    building = models.ForeignKey(
        Building,
        on_delete=models.CASCADE,
        related_name="mothballed_room_states",
    )
    room_profile = models.ForeignKey(
        _ROOM_PROFILE_FK,
        on_delete=models.CASCADE,
        related_name="+",
    )
    was_public = models.BooleanField(
        help_text="RoomProfile.is_public value at mothball time, restored on return.",
    )

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["building", "room_profile"],
                name="buildings_mothballed_room_state_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"mothball snapshot: room {self.room_profile_id} (was_public={self.was_public})"
