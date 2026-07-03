"""Models for the battles system.

A Battle is a 1:1 extension of scenes.Scene, mirroring Covenant↔Organization.
It owns two sides, named fronts (places), abstract enemy/friendly units, a round
lifecycle, and per-participant declarations.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.battles.constants import (
    DEFAULT_ROUND_LIMIT,
    DEFAULT_VICTORY_THRESHOLD,
    BattleActionKind,
    BattleActionScope,
    BattleOutcome,
    BattleParticipantStatus,
    BattlePosture,
    BattleSideRole,
    BattleUnitStatus,
    TerrainType,
    UnitComposition,
    UnitQuality,
)
from world.scenes.constants import RoundStatus
from world.scenes.round_models import AbstractRound

# Lazy model references extracted to constants to satisfy S1192.
SCENE_MODEL = "scenes.Scene"
STORY_MODEL = "stories.Story"
COMBAT_ENCOUNTER_MODEL = "combat.CombatEncounter"
CHARACTER_SHEET_MODEL = "character_sheets.CharacterSheet"
TECHNIQUE_MODEL = "magic.Technique"
COVENANT_MODEL = "covenants.Covenant"


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
        help_text="Authored cost for a future reposition action (#1712) to consume. "
        "This field is data only — #1711 does not build a movement action.",
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
        "— composition/quality below drive mechanics.",
    )
    composition = models.CharField(
        max_length=20,
        choices=UnitComposition.choices,
        default=UnitComposition.IRREGULAR,
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
    status = models.CharField(
        max_length=20,
        choices=BattleUnitStatus.choices,
        default=BattleUnitStatus.ACTIVE,
    )

    class Meta:
        ordering = ["battle", "side", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.composition}) [{self.get_status_display()}]"


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


class TechniqueCompositionAffinity(SharedMemoryModel):
    """Authored (technique, composition) -> flat STRIKE-check modifier (#1711).

    Positive = the technique is especially effective against that composition;
    negative = weak against it. Looked up by BattleTechniqueResolver when the
    declaration's target_unit.composition matches a row.
    """

    technique = models.ForeignKey(
        TECHNIQUE_MODEL,
        on_delete=models.PROTECT,
        related_name="battle_composition_affinities",
    )
    composition = models.CharField(max_length=20, choices=UnitComposition.choices)
    modifier = models.SmallIntegerField()

    class Meta:
        ordering = ["technique", "composition"]
        constraints = [
            models.UniqueConstraint(
                fields=["technique", "composition"],
                name="unique_technique_composition_affinity",
            )
        ]

    def __str__(self) -> str:
        return f"{self.technique.name} vs {self.get_composition_display()}: {self.modifier:+d}"


class TerrainCompositionEffect(SharedMemoryModel):
    """Authored (terrain_type, composition) -> flat attacker-facing STRIKE modifier (#1711).

    Positive = that composition is easier to strike in that terrain; negative = harder.
    Looked up by BattleTechniqueResolver against the target unit's place.terrain_type.
    """

    terrain_type = models.CharField(max_length=20, choices=TerrainType.choices)
    composition = models.CharField(max_length=20, choices=UnitComposition.choices)
    modifier = models.SmallIntegerField()

    class Meta:
        ordering = ["terrain_type", "composition"]
        constraints = [
            models.UniqueConstraint(
                fields=["terrain_type", "composition"],
                name="unique_terrain_composition_effect",
            )
        ]

    def __str__(self) -> str:
        return (
            f"{self.get_terrain_type_display()} vs {self.get_composition_display()}: "
            f"{self.modifier:+d}"
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
