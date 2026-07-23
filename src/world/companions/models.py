"""Models for the Companion substrate (#672).

Binding is archetype-selection, not a real in-room-creature target — see the
#672 spec's Decision #15. CompanionArchetype is the staff-authored catalog;
Companion (added in Task 2) is the per-PC bound instance.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from actions.constants import ActionCategory
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.combat.constants import OpponentTier
from world.companions.constants import CompanionAbilityKind, CompanionDomain, CompanionOrderKind


class CompanionArchetype(NaturalKeyMixin, SharedMemoryModel):
    """Staff-authored catalog row for a bindable companion archetype.

    A PC binds an instance of an archetype (e.g. "Direwolf") rather than a
    specific in-room creature object.
    """

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    domain = models.CharField(
        max_length=20,
        choices=CompanionDomain.choices,
        default=CompanionDomain.BEAST,
    )
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    bind_difficulty = models.PositiveSmallIntegerField(
        help_text="Feeds perform_check's target_difficulty for the bind attempt.",
    )
    capacity_cost = models.PositiveSmallIntegerField(
        help_text="Companion Capacity consumed while this archetype is bonded.",
    )
    charm_difficulty_reduction = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Reduction to bind_difficulty when binding a charmed target. "
            "0 = no charm bonus; equal to bind_difficulty = auto-success. "
            "Per-archetype staff-tunable knob (#2502)."
        ),
    )
    # Combat stats for bridging into encounters/battles (#1873).
    max_health = models.PositiveSmallIntegerField(
        default=30,
        help_text="Max health when bridged into a CombatOpponent (manual mode).",
    )
    soak_value = models.PositiveSmallIntegerField(
        default=0,
        help_text="Damage mitigation when bridged into a CombatOpponent.",
    )
    tier = models.CharField(
        max_length=20,
        choices=OpponentTier.choices,
        default=OpponentTier.MOOK,
        help_text="Opponent tier when bridged into a CombatOpponent.",
    )
    strength = models.PositiveSmallIntegerField(
        default=5,
        help_text="Unit strength when bridged into a BattleVehicle.",
    )
    is_mount = models.BooleanField(
        default=False,
        help_text=(
            "Whether this archetype is a ridable mount. Descriptive tag "
            "for now — mount-riding mechanics are deferred (#1863)."
        ),
    )

    class Meta:
        ordering = ["domain", "name"]
        verbose_name = "Companion Archetype"
        verbose_name_plural = "Companion Archetypes"

    def __str__(self) -> str:
        return self.name


class CompanionAbility(NaturalKeyMixin, SharedMemoryModel):
    """Staff-authored ability a companion archetype can perform (#1921).

    ATTACK abilities carry damage stats (mirroring ThreatPoolEntry columns).
    UTILITY abilities grant a Property (e.g. FLYING) for the round.
    ATTACK abilities link to a Technique for battle-scale resolution.
    """

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    archetype = models.ForeignKey(
        CompanionArchetype,
        on_delete=models.CASCADE,
        related_name="abilities",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    ability_kind = models.CharField(
        max_length=10,
        choices=CompanionAbilityKind.choices,
        default=CompanionAbilityKind.ATTACK,
    )
    # Attack fields (inert when UTILITY)
    attack_category = models.CharField(
        max_length=20,
        choices=ActionCategory.choices,
        blank=True,
        default="",
    )
    base_damage = models.PositiveIntegerField(default=0)
    damage_type = models.ForeignKey(
        "conditions.DamageType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="companion_abilities",
    )
    conditions_applied = models.ManyToManyField(
        "conditions.ConditionTemplate",
        blank=True,
        related_name="companion_abilities",
    )
    effect_properties = models.ManyToManyField(
        "mechanics.Property",
        blank=True,
        related_name="companion_abilities",
    )
    # Utility fields (inert when ATTACK)
    grants_property = models.ForeignKey(
        "mechanics.Property",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="granted_by_companion_abilities",
    )
    # Battle-scale bridge: the Technique this ability resolves as
    technique = models.ForeignKey(
        "magic.Technique",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="companion_abilities",
    )
    weight = models.PositiveIntegerField(
        default=10,
        help_text="Selection weight when auto-attacking (no order).",
    )

    class Meta:
        ordering = ["archetype", "name"]
        verbose_name = "Companion Ability"
        verbose_name_plural = "Companion Abilities"
        constraints = [
            models.UniqueConstraint(
                fields=["archetype", "name"],
                name="unique_ability_per_archetype",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.archetype.name})"

    def clean(self) -> None:
        super().clean()
        if self.ability_kind == CompanionAbilityKind.ATTACK:
            if not self.attack_category:
                msg = "ATTACK abilities must set attack_category."
                raise ValidationError(msg)
        elif self.ability_kind == CompanionAbilityKind.UTILITY:
            if self.grants_property is None:
                msg = "UTILITY abilities must set grants_property."
                raise ValidationError(msg)


class Companion(SharedMemoryModel):
    """A PC's bound companion — the persistent, room-present instance.

    Domain lives on ``archetype.domain``, not duplicated here — binding is
    archetype-selection (see the docstring on ``CompanionArchetype``).
    """

    owner = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.PROTECT,
        related_name="companions",
    )
    archetype = models.ForeignKey(
        CompanionArchetype,
        on_delete=models.PROTECT,
        related_name="companions",
    )
    granting_gift = models.ForeignKey(
        "magic.Gift",
        on_delete=models.PROTECT,
        related_name="granted_companions",
        help_text="Which Gift's Thread capacity pool this companion is charged against.",
    )
    name = models.CharField(max_length=100)
    # ObjectDB by design (#2608): a CompanionObject typeclass instance — a creature
    # with no CharacterSheet by design (companion mechanics live on this model).
    objectdb = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="companion_rows",
        help_text="The in-world CompanionObject representation. Set at bind, "
        "cleared if destroyed externally or on release.",
    )
    bonded_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)
    ridden_by = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        unique=True,
        related_name="ridden_companion",
        help_text=(
            "The rider currently mounted on this companion (#1843). Unique — a "
            "CharacterSheet can ride at most one companion at a time. Requires "
            "archetype.is_mount; set/cleared by mount_companion/dismount_companion."
        ),
    )

    class Meta:
        ordering = ["-bonded_at"]
        verbose_name = "Companion"
        verbose_name_plural = "Companions"

    def __str__(self) -> str:
        return f"{self.name} ({self.archetype.name})"

    @property
    def is_active(self) -> bool:
        return self.released_at is None


class CompanionDeployment(SharedMemoryModel):
    """Links a persistent ``Companion`` to its in-battle ``BattleVehicle``.

    Lives in ``companions`` (not ``battles``) per ADR-0010: the FK points from
    the more specific/dependent system (companions) at the reusable battle
    primitives, so ``battles`` stays free of a companions import — mirroring
    ``ShipDeployment`` in ``world/ships/models.py``.
    """

    companion = models.ForeignKey(
        Companion,
        on_delete=models.CASCADE,
        related_name="deployments",
    )
    battle = models.ForeignKey(
        "battles.Battle",
        on_delete=models.CASCADE,
        related_name="companion_deployments",
    )
    vehicle = models.OneToOneField(
        "battles.BattleVehicle",
        on_delete=models.CASCADE,
        related_name="companion_deployment",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["battle", "companion"]

    def __str__(self) -> str:
        return f"Deployment of companion {self.companion_id} into battle {self.battle_id}"


class CompanionOrder(SharedMemoryModel):
    """Round-scoped directive linking a companion to its order (#1921).

    One order per companion per round per scale (duel/battle).
    The round-tick reads this to override auto-selected behavior.
    """

    companion = models.ForeignKey(
        Companion,
        on_delete=models.CASCADE,
        related_name="orders",
    )
    encounter = models.ForeignKey(
        "combat.CombatEncounter",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="companion_orders",
    )
    battle = models.ForeignKey(
        "battles.Battle",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="companion_orders",
    )
    round_number = models.PositiveIntegerField()
    order_kind = models.CharField(
        max_length=20,
        choices=CompanionOrderKind.choices,
    )
    ability = models.ForeignKey(
        CompanionAbility,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    target_opponent = models.ForeignKey(
        "combat.CombatOpponent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    target_unit = models.ForeignKey(
        "battles.BattleUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    defending_participant = models.ForeignKey(
        "combat.CombatParticipant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    target_ally = models.ForeignKey(
        "battles.BattleParticipant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["companion", "encounter", "round_number"],
                name="unique_order_per_companion_per_duel_round",
            ),
            models.UniqueConstraint(
                fields=["companion", "battle", "round_number"],
                name="unique_order_per_companion_per_battle_round",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.companion.name} R{self.round_number}: {self.get_order_kind_display()}"

    def clean(self) -> None:
        super().clean()
        if self.encounter is None and self.battle is None:
            msg = "CompanionOrder requires either an encounter or a battle."
            raise ValidationError(msg)
        if self.encounter is not None and self.battle is not None:
            msg = "CompanionOrder cannot have both an encounter and a battle."
            raise ValidationError(msg)


class StablesDetails(SharedMemoryModel):
    """Per-instance config for a Stables RoomFeatureInstance (#1863).

    Follows the SanctumDetails pattern: OneToOne → RoomFeatureInstance,
    carrying per-instance tuning knobs. The Stables' mechanical effect
    (capacity bonus) is derive-on-read via
    :func:`world.companions.services.stables_capacity_bonus_for_sheet`.
    """

    feature_instance = models.OneToOneField(
        "room_features.RoomFeatureInstance",
        on_delete=models.CASCADE,
        related_name="stables_details",
        primary_key=True,
    )
    capacity_bonus_per_level = models.PositiveSmallIntegerField(
        default=1,
        help_text=(
            "Flat Companion Capacity bonus per Stables level. "
            "Total bonus = capacity_bonus_per_level * instance.level."
        ),
    )

    class Meta:
        ordering = ["feature_instance"]

    def __str__(self) -> str:
        return f"Stables details ({self.capacity_bonus_per_level}/level)"
