"""Models for the battles system.

A Battle is a 1:1 extension of scenes.Scene, mirroring Covenant↔Organization.
It owns two sides, named fronts (places), abstract enemy/friendly units, a round
lifecycle, and per-participant declarations.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

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
)
from world.conditions.models import CapabilityType
from world.mechanics.models import Property
from world.scenes.constants import RoundStatus
from world.scenes.round_models import AbstractRound

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
    afk_peril_override = models.BooleanField(
        default=False,
        help_text=(
            "When true, a Surrounded participant's peril escalates every round the GM "
            "resolves regardless of whether they declared this round (narrow, explicit "
            "ADR-0004 exception scoped to peril only — see ADR-0074)."
        ),
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
    name = models.CharField(max_length=120)
    descriptor = models.CharField(
        max_length=80,
        blank=True,
        help_text="Optional flavor tag (e.g. 'zombies-on-nightmares'). Narrative only "
        "— properties/capabilities/quality below drive mechanics.",
    )
    properties = models.ManyToManyField(
        Property,
        blank=True,
        related_name="battle_units",
        help_text="Descriptive tags this unit carries (flying, aquatic, metal-clad, "
        "etc.) — the same catalog characters use (#1794). Presence-only, no per-unit "
        "magnitude (matches how Property is consumed everywhere else).",
    )
    capabilities = models.ManyToManyField(
        CapabilityType,
        through="BattleUnitCapability",
        blank=True,
        related_name="battle_units",
        help_text="What this unit can DO, at an authored per-unit magnitude via "
        "BattleUnitCapability (#1794) — e.g. two units can both hold FLYING at "
        "very different values.",
    )
    individual_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Population data point mirroring CombatOpponent.swarm_count's "
        "naming/shape (#1794) — null means 'not a swarm-style unit'. No swarm-math "
        "resolution is wired against this field yet; that is left to #1714 "
        "(naval/aerial units) or a future issue that needs it.",
    )
    quality = models.CharField(
        max_length=20,
        choices=UnitQuality.choices,
        default=UnitQuality.TRAINED,
    )
    commander = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commanded_battle_units",
        help_text="Optional commander whose Battle Command modifier bonus applies to "
        "participants fighting alongside this unit's side/place.",
    )
    summoned_by = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="summoned_battle_units",
        help_text="Set when this unit was created via a military-grade summon (#1711).",
    )
    strength = models.PositiveSmallIntegerField(default=100)
    morale = models.PositiveSmallIntegerField(
        default=DEFAULT_MORALE,
        help_text="Second resource alongside strength (#1712). status is always "
        "derived from whichever resource crosses its own threshold first — see "
        "world.battles.resolution._compute_unit_status. Unlike strength (starts at "
        "its ceiling), morale starts well below it — sitting near MAX_MORALE is rare.",
    )
    status = models.CharField(
        max_length=20,
        choices=BattleUnitStatus.choices,
        default=BattleUnitStatus.ACTIVE,
    )

    class Meta:
        ordering = ["battle", "side", "name"]

    def __str__(self) -> str:
        return f"{self.name} [{self.get_status_display()}]"

    def effective_capability(self, capability: CapabilityType) -> int:
        """Authored magnitude for this unit's hold on ``capability``, 0 if absent.

        Conforms to world.mechanics.types.HasCapabilities alongside
        CharacterSheet (#1794).
        """
        row = self.capability_values.filter(capability=capability).first()
        return row.value if row is not None else 0

    def has_property(self, prop: Property) -> bool:
        """True if this unit carries ``prop``.

        Conforms to world.mechanics.types.HasProperties alongside
        CharacterSheet (#1794).
        """
        return self.properties.filter(pk=prop.pk).exists()


class BattleUnitCapability(SharedMemoryModel):
    """Authored (unit, capability) -> magnitude row (#1794).

    Mirrors ObjectProperty's shape (object/property/value,
    world/mechanics/models.py:589-618) one FK swapped: BattleUnit for ObjectDB,
    CapabilityType for Property. No source-tracking FKs — BattleUnit capabilities
    are static authored data, not subject to reactive conditions/challenges.
    """

    unit = models.ForeignKey(
        BattleUnit,
        on_delete=models.CASCADE,
        related_name="capability_values",
    )
    capability = models.ForeignKey(
        CapabilityType,
        on_delete=models.PROTECT,
        related_name="battle_unit_values",
    )
    value = models.PositiveIntegerField()

    class Meta:
        ordering = ["unit", "capability"]
        constraints = [
            models.UniqueConstraint(
                fields=["unit", "capability"],
                name="unique_battle_unit_capability",
            )
        ]

    def __str__(self) -> str:
        return f"{self.unit.name} {self.capability.name}: {self.value}"


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
        help_text="Targeting breadth (#1710) — UNIT/PLACE/SIDE.",
    )
    target_place = models.ForeignKey(
        BattlePlace,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scoped_declarations",
        help_text="Set when scope=PLACE.",
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
