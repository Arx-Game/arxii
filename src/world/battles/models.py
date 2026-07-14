"""Models for the battles system.

A Battle is a 1:1 extension of scenes.Scene, mirroring Covenant↔Organization.
It owns two sides, named fronts (places), abstract enemy/friendly units, a round
lifecycle, and per-participant declarations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager
from world.battles.constants import (
    DEFAULT_MORALE,
    DEFAULT_ROUND_LIMIT,
    DEFAULT_VICTORY_THRESHOLD,
    BattleActionKind,
    BattleActionScope,
    BattleOutcome,
    BattleParticipantStatus,
    BattlePosture,
    BattleSideRole,
    BattleUnitStatus,
    FortificationKind,
    TerrainType,
    UnitQuality,
    VehicleKind,
)
from world.checks.models import OutcomeTierAward
from world.combat.constants import RiskLevel
from world.conditions.models import CapabilityType
from world.mechanics.models import Property
from world.scenes.constants import RoundStatus
from world.scenes.round_models import AbstractRound
from world.weather.models import WeatherType

if TYPE_CHECKING:
    from world.battles.state_cache import BattleStateCache

# Lazy model references extracted to constants to satisfy S1192.
SCENE_MODEL = "scenes.Scene"
STORY_MODEL = "stories.Story"
COMBAT_ENCOUNTER_MODEL = "combat.CombatEncounter"
CHARACTER_SHEET_MODEL = "character_sheets.CharacterSheet"
TECHNIQUE_MODEL = "magic.Technique"
COVENANT_MODEL = "covenants.Covenant"
BUILDING_MODEL = "buildings.Building"


class Battle(SharedMemoryModel):
    """A large-scale battle scene extending scenes.Scene.

    The backing Scene is auto-created in save() when scene_id is None, wrapped
    in transaction.atomic() so a failure in either rolls back both.
    Never use bulk_create() for Battle.
    """

    scene = models.OneToOneField(
        SCENE_MODEL,
        on_delete=models.CASCADE,
        related_name="battle",
    )
    name = models.CharField(max_length=120)
    campaign_story = models.ForeignKey(
        STORY_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="battles",
        help_text="Optional campaign story this battle belongs to.",
    )
    round_limit = models.PositiveSmallIntegerField(
        default=DEFAULT_ROUND_LIMIT,
        help_text="Maximum number of rounds before the battle auto-concludes.",
    )
    outcome = models.CharField(
        max_length=30,
        choices=BattleOutcome.choices,
        default=BattleOutcome.UNRESOLVED,
    )
    concluded_at = models.DateTimeField(null=True, blank=True)
    is_paused = models.BooleanField(
        default=False,
        help_text=(
            "Set when a participant disconnects (#1899) — see maybe_pause_battle_for_disconnect."
        ),
    )
    afk_peril_override = models.BooleanField(
        default=False,
        help_text=(
            "When true, a Surrounded participant's peril escalates every round the GM "
            "resolves regardless of whether they declared this round (narrow, explicit "
            "ADR-0004 exception scoped to peril only — see ADR-0074)."
        ),
    )
    risk_level = models.CharField(
        max_length=10,
        choices=RiskLevel.choices,
        default=RiskLevel.LOW,
        help_text=(
            "Stakes axis for companion death-gating (#1873). "
            "EXTREME/LETHAL make companion death possible on defeat. "
            "Mirrors CombatEncounter.risk_level."
        ),
    )
    region = models.ForeignKey(
        "areas.Area",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="battles",
        help_text="Optional region anchor for ambient weather resolution (#1715). "
        "Battles are otherwise location-less (ADR-0081) — this is additive, not a "
        "return to room-graph coupling.",
    )
    weather_override = models.ForeignKey(
        WeatherType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="overriding_battles",
        help_text="Battle-wide cast-set weather (#1715); takes precedence over "
        "ambient (via region) when present. Cleared at round-boundary expiry.",
    )
    weather_override_expires_round = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Absolute round number this battle's weather_override expires at "
        "(#1715). Cleared alongside weather_override at round-boundary expiry.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: object, **kwargs: object) -> None:
        if self.scene_id is None:
            from django.db import transaction  # noqa: PLC0415

            from world.scenes.models import Scene  # noqa: PLC0415

            with transaction.atomic():
                self.scene = Scene.objects.create(name=self.name, location=None)
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)

    @property
    def is_concluded(self) -> bool:
        """True when the battle has a non-UNRESOLVED outcome."""
        return self.outcome != BattleOutcome.UNRESOLVED

    @property
    def current_round(self) -> BattleRound | None:
        """Latest non-completed round, or None."""
        return self.rounds.exclude(status=RoundStatus.COMPLETED).order_by("-round_number").first()

    @property
    def state_cache(self) -> BattleStateCache:
        """Per-battle roster cache -- see world.battles.state_cache.BattleStateCache."""
        if not hasattr(self, "_state_cache"):
            from world.battles.state_cache import BattleStateCache  # noqa: PLC0415

            self._state_cache = BattleStateCache(battle=self)
        return self._state_cache


class BattleSide(SharedMemoryModel):
    """One side in a battle (attacker or defender) with its victory-point tally."""

    battle = models.ForeignKey(
        Battle,
        on_delete=models.CASCADE,
        related_name="sides",
    )
    role = models.CharField(
        max_length=20,
        choices=BattleSideRole.choices,
        default=BattleSideRole.ATTACKER,
    )
    covenant = models.ForeignKey(
        COVENANT_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="battle_sides",
        help_text="The War Covenant fielding this side, if any (#1710).",
    )
    victory_points = models.PositiveIntegerField(default=0)
    victory_threshold = models.PositiveIntegerField(default=DEFAULT_VICTORY_THRESHOLD)
    posture = models.CharField(
        max_length=20,
        choices=BattlePosture.choices,
        default=BattlePosture.BALANCED,
    )

    class Meta:
        ordering = ["battle", "role"]
        constraints = [
            models.UniqueConstraint(
                fields=["battle", "role"],
                name="unique_battle_side_role",
            )
        ]

    def __str__(self) -> str:
        return f"{self.battle.name} — {self.get_role_display()}"

    def save(self, *args, **kwargs) -> None:
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            self.battle.state_cache.register_side(self)


class BattlePlace(SharedMemoryModel):
    """A named front or zone within a battle (e.g. 'The Main Gates')."""

    battle = models.ForeignKey(
        Battle,
        on_delete=models.CASCADE,
        related_name="places",
    )
    name = models.CharField(max_length=120)
    combat_encounter = models.ForeignKey(
        COMBAT_ENCOUNTER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="battle_places",
        help_text="Bridge seam: discrete combat taking place at this front.",
    )
    terrain_type = models.CharField(
        max_length=20,
        choices=TerrainType.choices,
        default=TerrainType.OPEN,
    )
    movement_cost = models.PositiveSmallIntegerField(
        default=1,
        help_text="Authored cost for a future reposition/movement action — not yet "
        "filed as an issue; #1712 explicitly did not build this. Data only.",
    )
    controlled_by = models.ForeignKey(
        BattleSide,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="controlled_places",
        help_text="Which side currently holds this front as an objective (#1712, "
        "set by a successful HOLD declaration). None means uncontrolled/contested.",
    )
    weather_override = models.ForeignKey(
        WeatherType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="overriding_battle_places",
        help_text="Local weather exception at this front (#1715) — beats the "
        "Battle-level weather_override/ambient value here only (cover, wards, a "
        "hostile local squall). Cleared at round-boundary expiry.",
    )
    weather_override_expires_round = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Absolute round number this place's weather_override expires at "
        "(#1715). Cleared alongside weather_override at round-boundary expiry.",
    )
    x = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text="Position on the battle's internal battle-map coordinate plane "
        "(#1714). Additive to ADR-0081, which only rejected anchoring BattlePlace "
        "to the room-level Position/PositionEdge graph — see ADR-0085.",
    )
    y = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    footprint_radius = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=1,
        help_text="How much of the battle-map grid this place occupies (#1714). "
        "Two places overlap when the distance between their (x, y) centers is "
        "less than the sum of their footprint_radius values.",
    )

    class Meta:
        ordering = ["battle", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["battle", "name"],
                name="unique_battle_place_name",
            )
        ]

    def __str__(self) -> str:
        return f"{self.battle.name} / {self.name}"

    def save(self, *args, **kwargs) -> None:
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            self.battle.state_cache.register_place(self)


class Fortification(SharedMemoryModel):
    """A defensible structure (wall/gate/battlement) at a battle front (#1713).

    A BattlePlace may have multiple Fortification rows — a front can have an
    outer wall, a gate, and a battlement, each independently breachable
    (ADR-0082's flagged siege reconsideration point, resolved in favor of
    per-structure state — see docs/adr/0083). ``defending_side`` gates which
    side may BREACH vs FORTIFY it (see ``declare_battle_action``).
    """

    place = models.ForeignKey(
        BattlePlace,
        on_delete=models.CASCADE,
        related_name="fortifications",
    )
    defending_side = models.ForeignKey(
        BattleSide,
        on_delete=models.CASCADE,
        related_name="fortifications",
        help_text="The side this structure protects. BREACH requires the declaring "
        "participant's side to differ from this; FORTIFY requires it to match (#1713).",
    )
    building = models.ForeignKey(
        BUILDING_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="battle_fortifications",
        help_text="Optional persistent Building this structure derives its integrity "
        "ceiling from (#1713). None means an ad-hoc, non-persistent structure.",
    )
    kind = models.CharField(
        max_length=20,
        choices=FortificationKind.choices,
        default=FortificationKind.WALL,
    )
    integrity = models.PositiveSmallIntegerField(default=0)
    max_integrity = models.PositiveSmallIntegerField(
        default=0,
        help_text="Snapshotted once at creation from BASE_INTEGRITY[kind] plus "
        "building.fortification_level * FORTIFICATION_LEVEL_INTEGRITY_BONUS, if "
        "building is set (#1713). See world.battles.services.create_fortification.",
    )
    breached = models.BooleanField(default=False)

    class Meta:
        ordering = ["place", "kind", "id"]

    def __str__(self) -> str:
        state = "breached" if self.breached else f"{self.integrity}/{self.max_integrity}"
        return f"{self.place.name} {self.get_kind_display()} ({state})"

    def save(self, *args, **kwargs) -> None:
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            self.place.battle.state_cache.register_fortification(self)


class BattleUnit(SharedMemoryModel):
    """An abstract typed force (enemy or friendly) at a particular front."""

    battle = models.ForeignKey(
        Battle,
        on_delete=models.CASCADE,
        related_name="units",
    )
    side = models.ForeignKey(
        BattleSide,
        on_delete=models.CASCADE,
        related_name="units",
    )
    place = models.ForeignKey(
        BattlePlace,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="units",
    )
    transit_x = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="In-progress MOVE position on the battle-map coordinate plane "
        "(#2007). Null when at rest — effective position is then simply this "
        "unit's .place coordinates. Mirrors BattlePlace.x's shape.",
    )
    transit_y = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    transit_target_place = models.ForeignKey(
        BattlePlace,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="units_in_transit",
        help_text="Destination of an in-progress multi-round MOVE (#2007). Null when at rest.",
    )
    military_unit = models.ForeignKey(
        "military.MilitaryUnit",
        on_delete=models.PROTECT,
        related_name="battle_units",
        help_text="The persistent MilitaryUnit this battle unit projects from. "
        "All identity and stats live on MilitaryUnit (ADR-0014, ADR-0125).",
    )
    status = models.CharField(
        max_length=20,
        choices=BattleUnitStatus.choices,
        default=BattleUnitStatus.ACTIVE,
    )

    class Meta:
        ordering = ["battle", "side", "military_unit__name"]

    def __str__(self) -> str:
        return f"{self.name} [{self.get_status_display()}]"

    # --- Proxy properties: delegate to military_unit for backward compat ---
    # Reads are transparent (unit.strength works); writes must go through
    # unit.military_unit.strength = ...; unit.military_unit.save().

    @property
    def name(self) -> str:
        return self.military_unit.name

    @property
    def descriptor(self) -> str:
        return self.military_unit.descriptor

    @property
    def quality(self) -> str:
        return self.military_unit.quality

    @property
    def commander(self):
        return self.military_unit.commander

    @property
    def summoned_by(self):
        return self.military_unit.summoned_by

    @property
    def strength(self) -> int:
        return self.military_unit.strength

    @property
    def morale(self) -> int:
        return self.military_unit.morale

    @property
    def individual_count(self):
        return self.military_unit.individual_count

    def effective_capability(self, capability: CapabilityType) -> int:
        """Authored magnitude for this unit's hold on ``capability``, 0 if absent.

        Delegates to the underlying MilitaryUnit (#1794). Conforms to
        world.mechanics.types.HasCapabilities alongside CharacterSheet.
        """
        return self.military_unit.effective_capability(capability)

    def has_property(self, prop: Property) -> bool:
        """True if this unit carries ``prop``.

        Delegates to the underlying MilitaryUnit (#1794). Conforms to
        world.mechanics.types.HasProperties alongside CharacterSheet.
        """
        return self.military_unit.has_property(prop)

    def save(self, *args, **kwargs) -> None:
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            self.battle.state_cache.register_unit(self)


class BattleRound(AbstractRound):
    """One round of a battle's declaration/resolution cycle."""

    battle = models.ForeignKey(
        Battle,
        on_delete=models.CASCADE,
        related_name="rounds",
    )

    class Meta:
        ordering = ["battle", "round_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["battle"],
                condition=models.Q(
                    status__in=[
                        RoundStatus.DECLARING,
                        RoundStatus.RESOLVING,
                        RoundStatus.BETWEEN_ROUNDS,
                    ]
                ),
                name="unique_active_battle_round",
            )
        ]

    def __str__(self) -> str:
        return f"{self.battle.name} — round {self.round_number}"


class BattleParticipant(SharedMemoryModel):
    """A player character enlisted in a battle on one side."""

    battle = models.ForeignKey(
        Battle,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="battle_participations",
    )
    side = models.ForeignKey(
        BattleSide,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    place = models.ForeignKey(
        BattlePlace,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="participants",
    )
    transit_x = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="In-progress MOVE position on the battle-map coordinate plane "
        "(#2007). Null when at rest — effective position is then simply this "
        "participant's .place coordinates. Mirrors BattlePlace.x's shape.",
    )
    transit_y = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    transit_target_place = models.ForeignKey(
        BattlePlace,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="participants_in_transit",
        help_text="Destination of an in-progress multi-round MOVE (#2007). Null when at rest.",
    )
    status = models.CharField(
        max_length=20,
        choices=BattleParticipantStatus.choices,
        default=BattleParticipantStatus.ACTIVE,
    )

    class Meta:
        ordering = ["battle", "character_sheet"]
        constraints = [
            models.UniqueConstraint(
                fields=["battle", "character_sheet"],
                name="unique_battle_participant",
            )
        ]

    def __str__(self) -> str:
        return f"{self.character_sheet} in {self.battle.name}"

    def save(self, *args, **kwargs) -> None:
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            self.battle.state_cache.register_participant(self)


class BattleActionDeclaration(SharedMemoryModel):
    """A participant's declared action for one round of a battle."""

    battle_round = models.ForeignKey(
        BattleRound,
        on_delete=models.CASCADE,
        related_name="declarations",
    )
    participant = models.ForeignKey(
        BattleParticipant,
        on_delete=models.CASCADE,
        related_name="declarations",
    )
    technique = models.ForeignKey(
        TECHNIQUE_MODEL,
        on_delete=models.PROTECT,
        related_name="battle_declarations",
        help_text="The technique cast for this declaration.",
    )
    action_kind = models.CharField(
        max_length=20,
        choices=BattleActionKind.choices,
        default=BattleActionKind.STRIKE,
    )
    target_unit = models.ForeignKey(
        BattleUnit,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="declarations",
    )
    target_ally = models.ForeignKey(
        BattleParticipant,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="support_declarations",
    )
    scope = models.CharField(
        max_length=10,
        choices=BattleActionScope.choices,
        default=BattleActionScope.UNIT,
        help_text="Targeting breadth (#1710) — UNIT/PLACE/SIDE/BATTLE.",
    )
    target_place = models.ForeignKey(
        BattlePlace,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scoped_declarations",
        help_text="Set when scope=PLACE, or as a MOVE destination regardless of "
        "scope (#2007) — null with action_kind=MOVE and scope=UNIT means withdraw.",
    )
    target_side = models.ForeignKey(
        BattleSide,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scoped_declarations",
        help_text="Set when scope=SIDE.",
    )
    target_fortification = models.ForeignKey(
        Fortification,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="declarations",
        help_text="Set when action_kind is BREACH or FORTIFY (#1713).",
    )
    reposition_dx = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Requested x-axis delta for a REPOSITION declaration (#1714). "
        "Clamped to the vehicle's SPEED capability magnitude at resolution.",
    )
    reposition_dy = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
    )
    resolved = models.BooleanField(default=False)
    success_level = models.SmallIntegerField(
        default=0,
        help_text="Check success level; >0 success, <=0 failure.",
    )

    class Meta:
        ordering = ["battle_round", "participant"]
        constraints = [
            models.UniqueConstraint(
                fields=["battle_round", "participant"],
                name="unique_battle_declaration_per_round",
            )
        ]

    def __str__(self) -> str:
        return (
            f"{self.participant} declares {self.get_action_kind_display()} in {self.battle_round}"
        )


class TechniquePropertyAffinity(SharedMemoryModel):
    """Authored (technique, property) -> flat STRIKE-check modifier (#1794).

    Positive = the technique is especially effective against that property;
    negative = weak against it. Summed across every one of a unit's properties
    that has a matching row — replaces #1711's TechniqueCompositionAffinity,
    which could only ever match a unit's single composition tag.
    """

    objects = ArxSharedMemoryManager()

    technique = models.ForeignKey(
        TECHNIQUE_MODEL,
        on_delete=models.PROTECT,
        related_name="battle_property_affinities",
    )
    property = models.ForeignKey(
        Property,
        on_delete=models.PROTECT,
        related_name="battle_technique_affinities",
    )
    modifier = models.SmallIntegerField()

    class Meta:
        ordering = ["technique", "property"]
        constraints = [
            models.UniqueConstraint(
                fields=["technique", "property"],
                name="unique_technique_property_affinity",
            )
        ]

    def __str__(self) -> str:
        return f"{self.technique.name} vs {self.property.name}: {self.modifier:+d}"


class TerrainPropertyEffect(SharedMemoryModel):
    """Authored (terrain_type, property) -> flat attacker-facing STRIKE modifier (#1794).

    Positive = a unit with that property is easier to strike in that terrain;
    negative = harder. Summed across every one of a unit's properties that has
    a matching row — replaces #1711's TerrainCompositionEffect.
    """

    objects = ArxSharedMemoryManager()

    terrain_type = models.CharField(max_length=20, choices=TerrainType.choices)
    property = models.ForeignKey(
        Property,
        on_delete=models.PROTECT,
        related_name="battle_terrain_effects",
    )
    modifier = models.SmallIntegerField()

    class Meta:
        ordering = ["terrain_type", "property"]
        constraints = [
            models.UniqueConstraint(
                fields=["terrain_type", "property"],
                name="unique_terrain_property_effect",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_terrain_type_display()} vs {self.property.name}: {self.modifier:+d}"


class WeatherTypePropertyEffect(SharedMemoryModel):
    """Authored (weather_type, property) -> flat check modifier (#1715).

    Positive = a unit with that property is easier to strike/affected under
    that weather; negative = harder. Summed across every one of a unit's
    properties that has a matching row — mirrors TerrainPropertyEffect, but
    keyed on the place's *effective* weather (resolution.effective_weather)
    rather than its static terrain_type.
    """

    objects = ArxSharedMemoryManager()

    weather_type = models.ForeignKey(
        WeatherType,
        on_delete=models.CASCADE,
        related_name="battle_property_effects",
    )
    property = models.ForeignKey(
        Property,
        on_delete=models.PROTECT,
        related_name="battle_weather_effects",
    )
    modifier = models.SmallIntegerField()

    class Meta:
        ordering = ["weather_type", "property"]
        constraints = [
            models.UniqueConstraint(
                fields=["weather_type", "property"],
                name="unique_weather_type_property_effect",
            )
        ]

    def __str__(self) -> str:
        return f"{self.weather_type.name} vs {self.property.name}: {self.modifier:+d}"


class WeatherTypeCapabilityChallenge(SharedMemoryModel):
    """Authored (weather_type, capability, threshold) -> flat modifier (#1715).

    Applies when a unit's effective_capability(capability) is strictly below
    threshold — e.g. a unit with no/low FLIGHT capability is penalized under
    Stormy weather. The first absence/threshold-based battle modifier in the
    codebase (everything else is presence- or >=-threshold based).
    """

    objects = ArxSharedMemoryManager()

    weather_type = models.ForeignKey(
        WeatherType,
        on_delete=models.CASCADE,
        related_name="battle_capability_challenges",
    )
    capability = models.ForeignKey(
        CapabilityType,
        on_delete=models.PROTECT,
        related_name="battle_weather_challenges",
    )
    threshold = models.PositiveIntegerField(
        help_text="Modifier applies when the unit's effective_capability for this "
        "capability is strictly below this value.",
    )
    modifier = models.SmallIntegerField()

    class Meta:
        ordering = ["weather_type", "capability"]
        constraints = [
            models.UniqueConstraint(
                fields=["weather_type", "capability"],
                name="unique_weather_type_capability_challenge",
            )
        ]

    def __str__(self) -> str:
        return (
            f"{self.weather_type.name} vs {self.capability.name} "
            f"< {self.threshold}: {self.modifier:+d}"
        )


class BattleOutcomeMapping(SharedMemoryModel):
    """Designer-tunable map from a Battle's graded outcome to a CheckOutcome tier.

    Used by ``classify_battle_conclusion_outcome`` (``world.battles.beat_wiring``)
    to select the CheckOutcome tier for beat completion when a war-scale Battle
    concludes (#1785). Unlike combat's ``EncounterOutcomeMapping``, there is no
    separate risk-level axis — ``BattleOutcome`` already encodes decisive-vs-marginal
    severity in its four resolved values. A missing row, or a row whose
    ``check_outcome`` is null, signals the caller to resolve the beat to
    PENDING_GM_REVIEW rather than firing a consequence pool. Starts empty; GMs
    author rows via admin.
    """

    outcome = models.CharField(max_length=30, choices=BattleOutcome.choices, unique=True)
    check_outcome = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="battle_outcome_mappings",
        help_text="CheckOutcome tier for this outcome. Null = resolve to PENDING_GM_REVIEW.",
    )

    class Meta:
        ordering = ["outcome"]

    def __str__(self) -> str:
        return f"BattleOutcomeMapping({self.get_outcome_display()})"


class BattleVehicle(SharedMemoryModel):
    """A vessel or great mount: pairs one BattleUnit (fights) with one BattlePlace
    (what units/PCs embed on) as a single in-fiction object (#1714).

    unit.place is intentionally left None — the vehicle's own Unit is not "at"
    a front, it IS the place other units/participants embed onto via their own
    place FK. Do not set unit.place to this vehicle's own place.
    """

    unit = models.OneToOneField(
        BattleUnit,
        on_delete=models.CASCADE,
        related_name="vehicle",
    )
    place = models.OneToOneField(
        BattlePlace,
        on_delete=models.CASCADE,
        related_name="vehicle",
    )
    vehicle_kind = models.CharField(
        max_length=20,
        choices=VehicleKind.choices,
        default=VehicleKind.SHIP,
    )
    is_structural = models.BooleanField(
        default=True,
        help_text="True for constructed vessels (ship/airship) — destruction "
        "goes through a hull Fortification breach. False for living mounts "
        "(dragon/kraken) — destruction reuses BattleUnitStatus.DESTROYED. "
        "Authored, not derived from vehicle_kind, so a future design can "
        "still model a 'living hull' if needed (#1714).",
    )

    def __str__(self) -> str:
        return f"{self.get_vehicle_kind_display()} ({self.place.name})"

    def save(self, *args, **kwargs) -> None:
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            self.unit.battle.state_cache.register_vehicle(self)


class BattleMapBlueprint(SharedMemoryModel):
    """Admin-authored, reusable battle-map layout a GM stages a Battle from (#2010).

    JUNIOR-trust GMs pick from this catalog rather than inventing terrain and
    fortification layouts from scratch — later tasks copy a blueprint's
    BlueprintBattlePlace/BlueprintFortification rows onto a live Battle's
    BattlePlace/Fortification rows.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive blueprints are hidden from the GM staging catalog "
        "but not deleted — existing data derived from them may still exist.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class BlueprintBattlePlace(SharedMemoryModel):
    """A named front/zone within a BattleMapBlueprint (#2010).

    Catalog-time counterpart to BattlePlace, copied onto a live Battle's
    BattlePlace rows when a GM stages a battle from this blueprint.
    """

    blueprint = models.ForeignKey(
        BattleMapBlueprint,
        on_delete=models.CASCADE,
        related_name="places",
    )
    name = models.CharField(max_length=100)
    terrain_type = models.CharField(
        max_length=20,
        choices=TerrainType.choices,
        default=TerrainType.OPEN,
    )
    movement_cost = models.PositiveSmallIntegerField(
        default=1,
        help_text="Authored cost carried over onto the staged BattlePlace's own "
        "movement_cost — see BattlePlace.movement_cost.",
    )
    x = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text="Position on the blueprint's battle-map coordinate plane, "
        "carried over onto the staged BattlePlace's own x/y (#1714).",
    )
    y = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    footprint_radius = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=1,
        help_text="How much of the battle-map grid this place occupies — see "
        "BattlePlace.footprint_radius.",
    )

    class Meta:
        ordering = ["blueprint", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["blueprint", "name"],
                name="unique_blueprint_place_name",
            )
        ]

    def __str__(self) -> str:
        return f"{self.blueprint.name} / {self.name}"


class BlueprintFortification(SharedMemoryModel):
    """Catalog-time counterpart to Fortification, owned by a BlueprintBattlePlace (#2010)."""

    blueprint_place = models.ForeignKey(
        BlueprintBattlePlace,
        on_delete=models.CASCADE,
        related_name="fortifications",
    )
    kind = models.CharField(
        max_length=20,
        choices=FortificationKind.choices,
        default=FortificationKind.WALL,
    )
    max_integrity = models.PositiveIntegerField(
        default=100,
        help_text="Carried over onto the staged Fortification's max_integrity "
        "(and starting integrity) — see Fortification.max_integrity.",
    )
    defending_side_role = models.CharField(
        max_length=20,
        choices=BattleSideRole.choices,
        help_text="Which staged BattleSide role this structure protects — resolved "
        "to a concrete BattleSide when the blueprint is staged onto a Battle.",
    )

    class Meta:
        ordering = ["blueprint_place", "kind", "id"]

    def __str__(self) -> str:
        return f"{self.blueprint_place.name} {self.get_kind_display()}"


class BattleUnitTemplate(SharedMemoryModel):
    """Admin-authored, reusable unit stat block a GM stages a Battle from (#2010).

    Catalog-time counterpart to BattleUnit — copied onto a live Battle's
    BattleUnit rows (along with properties/capabilities) when a GM stages a
    unit from this template.
    """

    name = models.CharField(max_length=100, unique=True)
    descriptor = models.CharField(max_length=200, blank=True, default="")
    quality = models.CharField(
        max_length=20,
        choices=UnitQuality.choices,
        default=UnitQuality.TRAINED,
    )
    strength = models.PositiveIntegerField(default=100)
    morale = models.PositiveIntegerField(default=DEFAULT_MORALE)
    individual_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Population data point mirroring BattleUnit.individual_count — "
        "null means 'not a swarm-style unit'.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive templates are hidden from the GM staging catalog but not deleted.",
    )
    properties = models.ManyToManyField(
        Property,
        blank=True,
        related_name="+",
        help_text="Descriptive tags carried over onto the staged BattleUnit's own "
        "properties — see BattleUnit.properties.",
    )
    capabilities = models.ManyToManyField(
        CapabilityType,
        through="BattleUnitTemplateCapability",
        blank=True,
        related_name="+",
        help_text="What a unit staged from this template can DO, at an authored "
        "per-template magnitude via BattleUnitTemplateCapability — see "
        "BattleUnit.capabilities.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class BattleUnitTemplateCapability(SharedMemoryModel):
    """Authored (template, capability) -> magnitude row (#2010).

    Catalog-time counterpart to BattleUnitCapability — carried over onto the
    staged BattleUnit's own BattleUnitCapability rows.
    """

    template = models.ForeignKey(
        BattleUnitTemplate,
        on_delete=models.CASCADE,
        related_name="capability_values",
    )
    capability = models.ForeignKey(
        CapabilityType,
        on_delete=models.PROTECT,
        related_name="battle_unit_template_values",
    )
    value = models.IntegerField(default=0)

    class Meta:
        ordering = ["template", "capability"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "capability"],
                name="unique_battle_unit_template_capability",
            )
        ]

    def __str__(self) -> str:
        return f"{self.template.name} {self.capability.name}: {self.value}"


class CityDefenseDetails(SharedMemoryModel):
    """Per-(CITY_DEFENSE Project) details payload (#1892).

    Staff create the project linked to an Area; players contribute during
    the preparation window; at the deadline progress is graded into a
    CheckOutcome tier via CityDefenseTierThreshold rows, and the handler
    stores the tier here. When a battle is later staged in that area,
    create_fortification reads the stored tier's integrity bonus and
    boosts the defending side's fortifications.
    """

    project = models.OneToOneField(
        "projects.Project",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="city_defense_details",
    )
    area = models.ForeignKey(
        "areas.Area",
        on_delete=models.PROTECT,
        related_name="city_defense_projects",
        help_text="The defended region. PROTECT prevents deleting an area with a defense project.",
    )
    outcome_tier = models.ForeignKey(
        "traits.CheckOutcome",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="city_defense_projects",
        help_text="The graded outcome tier, set when the handler runs at deadline.",
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the handler runs; idempotency guard (claim-filter pattern).",
    )

    def __str__(self) -> str:
        return f"CityDefense#{self.project_id}: {self.area_id}"


class CityDefenseTierThreshold(SharedMemoryModel):
    """A progress band on a CityDefenseDetails that grants a CheckOutcome tier.

    Tier reached at deadline = highest min_progress row whose
    min_progress <= project.current_progress. Seeded rows always include a
    baseline failure tier at min_progress=0 so every graded project maps to
    exactly one tier.
    """

    details = models.ForeignKey(
        CityDefenseDetails,
        on_delete=models.CASCADE,
        related_name="tier_thresholds",
    )
    outcome_tier = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.PROTECT,
        related_name="city_defense_thresholds",
    )
    min_progress = models.PositiveIntegerField(
        help_text="Minimum progress at which this tier applies.",
    )

    class Meta:
        ordering = ["-min_progress"]
        constraints = [
            models.UniqueConstraint(
                fields=["details", "outcome_tier"],
                name="uniq_city_defense_tier",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.outcome_tier} @ {self.min_progress}"


class CityDefenseIntegrityBonus(OutcomeTierAward):
    """Integrity bonus granted to defending fortifications for a CheckOutcome tier (#1892).

    Read by get_city_defense_integrity_bonus; a missing row yields 0 (a content
    gap, not a crash). Staff-tunable — no hardcoded bonuses in service code.
    """

    integrity_bonus = models.PositiveSmallIntegerField(
        help_text="Bonus added to Fortification.max_integrity for this tier.",
    )

    def __str__(self) -> str:
        return f"{self.outcome_tier}: +{self.integrity_bonus}"


class WarFundingDetails(SharedMemoryModel):
    """Per-(WAR_FUNDING Project) details payload (#1890).

    A covenant leader opens a war-funding project; members contribute during
    the preparation window; at the deadline progress is graded into a
    CheckOutcome tier via WarFundingTierThreshold rows, and the handler stores
    the tier here and updates CovenantMilitaryReadiness. When units are later
    mustered into a battle for this covenant, get_war_funding_bonus reads the
    stored tier's WarFundingTierBonus and applies the bonuses.
    """

    project = models.OneToOneField(
        "projects.Project",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="war_funding_details",
    )
    covenant = models.ForeignKey(
        "covenants.Covenant",
        on_delete=models.PROTECT,
        related_name="war_funding_projects",
        help_text="The covenant whose military readiness this drive funds.",
    )
    outcome_tier = models.ForeignKey(
        "traits.CheckOutcome",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="war_funding_projects",
        help_text="The graded outcome tier, set when the handler runs at deadline.",
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the handler runs; idempotency guard (claim-filter pattern).",
    )

    def __str__(self) -> str:
        return f"WarFunding#{self.project_id}: {self.covenant_id}"


class WarFundingTierThreshold(SharedMemoryModel):
    """A progress band on a WarFundingDetails that grants a CheckOutcome tier.

    Tier reached at deadline = highest min_progress row whose
    min_progress <= project.current_progress. Seeded rows always include a
    baseline failure tier at min_progress=0 so every graded project maps to
    exactly one tier.
    """

    details = models.ForeignKey(
        WarFundingDetails,
        on_delete=models.CASCADE,
        related_name="tier_thresholds",
    )
    outcome_tier = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.PROTECT,
        related_name="war_funding_thresholds",
    )
    min_progress = models.PositiveIntegerField(
        help_text="Minimum progress at which this tier applies.",
    )

    class Meta:
        ordering = ["-min_progress"]
        constraints = [
            models.UniqueConstraint(
                fields=["details", "outcome_tier"],
                name="uniq_war_funding_tier",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.outcome_tier} @ {self.min_progress}"


class WarFundingTierBonus(OutcomeTierAward):
    """Per-unit bonuses granted for a CheckOutcome tier (#1890).

    Read by get_war_funding_bonus; a missing row yields zero bonuses (content
    gap, not a crash). Staff-tunable — no hardcoded bonuses in service code.
    """

    quality_steps = models.PositiveSmallIntegerField(
        default=0,
        help_text="Quality upgrade steps applied at muster (0-2).",
    )
    strength_bonus = models.PositiveSmallIntegerField(
        default=0,
        help_text="Additive strength bonus per unit.",
    )
    morale_bonus = models.PositiveSmallIntegerField(
        default=0,
        help_text="Additive morale bonus per unit.",
    )
    training_xp = models.PositiveSmallIntegerField(
        default=0,
        help_text="Training experience added to CovenantMilitaryReadiness.",
    )

    def __str__(self) -> str:
        return (
            f"{self.outcome_tier}: +{self.quality_steps}q"
            f" +{self.strength_bonus}s +{self.morale_bonus}m"
        )


class CovenantMilitaryReadiness(SharedMemoryModel):
    """Persistent military training state for a covenant (#1890).

    Accumulates training_xp across multiple WAR_FUNDING projects. When
    training_level crosses ReadinessThreshold rows, additional quality steps
    are granted on top of the per-tier bump — so partial successes still
    matter over time.
    """

    covenant = models.OneToOneField(
        "covenants.Covenant",
        on_delete=models.CASCADE,
        related_name="military_readiness",
    )
    training_level = models.PositiveIntegerField(
        default=0,
        help_text="Accumulated training experience across WAR_FUNDING projects.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.covenant.name}: training {self.training_level}"


class ReadinessThreshold(SharedMemoryModel):
    """A global training-level band that grants bonus quality steps (#1890).

    Staff-tuned rows keyed by min_training_level only (global, not per-covenant).
    The highest min_training_level row at or below the covenant's current
    training_level determines the bonus quality steps.
    """

    min_training_level = models.PositiveIntegerField(
        help_text="Minimum training level at which this bonus applies.",
    )
    bonus_quality_steps = models.PositiveSmallIntegerField(
        default=0,
        help_text="Additional quality steps granted at this training level.",
    )

    class Meta:
        ordering = ["-min_training_level"]
        constraints = [
            models.UniqueConstraint(
                fields=["min_training_level"],
                name="uniq_readiness_threshold_level",
            ),
        ]

    def __str__(self) -> str:
        return f"training>={self.min_training_level}: +{self.bonus_quality_steps}q"
