"""Building system models.

Per the Plan 3 spec (#668):

- ``BuildingKind`` is an open catalog (rows, not enum) with non-exclusive
  descriptive boolean flags. Each row tunes ``rooms_per_size_tier``.
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

from django.core.validators import MinValueValidator
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class BuildingKind(SharedMemoryModel):
    """An authorable category of building.

    Open catalog — rows authored by staff, not an enum. Each row carries
    non-exclusive descriptive flags (a fortified floating witch-king
    manor is ``residential + fortified + occult + aerial``) plus the
    ``rooms_per_size_tier`` knob that drives the construction-time
    room budget formula.

    Per the brainstorm, the flag set is NOT a taxonomy. Flags are
    sort/filter axes used by authoring NPCs to decide what they issue
    permits for. Multiple flags can be true on one row.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(
        blank=True,
        help_text="Admin-editable flavor describing what this kind is.",
    )
    rooms_per_size_tier = models.PositiveIntegerField(
        default=1,
        help_text=(
            "Multiplier in the room-budget formula. "
            "``Building.max_rooms = rooms_per_size_tier × Project.target_size`` "
            "at construction. A House at 20 gives Size-1=20, Size-10=200 rooms. "
            "Witch's Cottage at 4 gives Size-10=40. Per-kind tuning."
        ),
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

    def __str__(self) -> str:
        return self.name


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
    kind = models.ForeignKey(
        BuildingKind,
        on_delete=models.PROTECT,
        related_name="buildings",
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
    max_rooms = models.PositiveIntegerField(
        help_text=(
            "Mutable room cap. Computed at construction as "
            "``kind.rooms_per_size_tier × target_size``. Raised by "
            "BUILDING_EXTENSION (#673), recalculated by BUILDING_UPGRADE."
        ),
    )
    constructed_at = models.DateTimeField(auto_now_add=True)
    constructed_by_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="buildings_constructed",
    )
    source_project = models.OneToOneField(
        "projects.Project",
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
        "scenes.Persona",
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
        "scenes.Persona",
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


class BuildingConstructionDetails(SharedMemoryModel):
    """Per-(BUILDING_CONSTRUCTION Project) details payload.

    Plan 1 set up the Project framework with per-kind details models;
    this is the one for the BUILDING_CONSTRUCTION kind. Created when
    a permit is activated and the construction project spawns; consumed
    by ``complete_building_construction`` when the project completes.
    """

    project = models.OneToOneField(
        "projects.Project",
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
        "scenes.Persona",
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
