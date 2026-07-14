"""Models for the military system.

MilitaryUnit is the persistent source of truth for a military unit's identity
and stats. It exists outside battles. BattleUnit (in world.battles) becomes a
thin join record referencing MilitaryUnit — no denormalized stats (ADR-0014).

Army groups one or more MilitaryUnits (possibly from different organizations)
into a persistent force for campaigns or defense.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.battles.constants import DEFAULT_MORALE, UnitQuality
from world.conditions.models import CapabilityType
from world.mechanics.models import Property

CHARACTER_SHEET_MODEL = "character_sheets.CharacterSheet"


class MilitaryUnit(SharedMemoryModel):
    """A persistent military unit — the single source of truth for identity and stats.

    Exists outside battles. BattleUnit references this via a FK. Enemy/summoned
    units are transient MilitaryUnits with null owner_org.

    Mirrors the fields formerly on BattleUnit (name, descriptor, quality,
    commander, summoned_by, strength, morale, individual_count, properties,
    capabilities) — moved here so the persistent unit carries its identity and
    stats between battles (ADR-0014: single source of truth).
    """

    name = models.CharField(max_length=120)
    descriptor = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="Optional flavor tag (e.g. 'zombies-on-nightmares'). Narrative only "
        "— properties/capabilities/quality below drive mechanics.",
    )
    owner_org = models.ForeignKey(
        "societies.Organization",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="military_units",
        help_text="The organization that owns this unit. Null for transient enemy/summoned units.",
    )
    commander = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commanded_military_units",
        help_text="Optional commander whose Battle Command modifier bonus applies to "
        "participants fighting alongside this unit's side/place.",
    )
    summoned_by = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="summoned_military_units",
        help_text="Set when this unit was created via a military-grade summon (#1711).",
    )
    quality = models.CharField(
        max_length=20,
        choices=UnitQuality.choices,
        default=UnitQuality.TRAINED,
    )
    strength = models.PositiveSmallIntegerField(default=100)
    morale = models.PositiveSmallIntegerField(
        default=DEFAULT_MORALE,
        help_text="Second resource alongside strength (#1712). Unlike strength "
        "(starts at its ceiling), morale starts well below it.",
    )
    individual_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Population data point mirroring CombatOpponent.swarm_count's "
        "naming/shape (#1794) — null means 'not a swarm-style unit'.",
    )
    properties = models.ManyToManyField(
        Property,
        blank=True,
        related_name="military_units",
        help_text="Descriptive tags this unit carries (flying, aquatic, metal-clad, "
        "etc.) — the same catalog characters use (#1794). Presence-only.",
    )
    capabilities = models.ManyToManyField(
        CapabilityType,
        through="MilitaryUnitCapability",
        blank=True,
        related_name="military_units",
        help_text="What this unit can DO, at an authored per-unit magnitude via "
        "MilitaryUnitCapability (#1794).",
    )

    class Meta:
        ordering = ["owner_org", "name"]

    def __str__(self) -> str:
        return self.name

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


class MilitaryUnitCapability(SharedMemoryModel):
    """Authored (unit, capability) -> magnitude row (#1794).

    Mirrors the former BattleUnitCapability shape — one FK swapped:
    MilitaryUnit for BattleUnit. No source-tracking FKs — capabilities are
    static authored data, not subject to reactive conditions/challenges.
    """

    unit = models.ForeignKey(
        MilitaryUnit,
        on_delete=models.CASCADE,
        related_name="capability_values",
    )
    capability = models.ForeignKey(
        CapabilityType,
        on_delete=models.PROTECT,
        related_name="military_unit_values",
    )
    value = models.PositiveIntegerField()

    class Meta:
        ordering = ["unit", "capability"]
        constraints = [
            models.UniqueConstraint(
                fields=["unit", "capability"],
                name="unique_military_unit_capability",
            )
        ]

    def __str__(self) -> str:
        return f"{self.unit.name} {self.capability.name}: {self.value}"


class Army(SharedMemoryModel):
    """A persistent grouping of MilitaryUnits formed for a campaign or defense.

    Armies can include units from different organizations (allied forces). An
    Army persists across battles — it can fight multiple battles in a campaign,
    then be disbanded. The optional covenant FK connects war covenants to
    armies.
    """

    name = models.CharField(max_length=120)
    commander = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commanded_armies",
        help_text="The overall commander of this army. May differ from individual unit commanders.",
    )
    campaign_story = models.ForeignKey(
        "stories.Story",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="armies",
        help_text="Optional campaign story this army was formed for.",
    )
    covenant = models.ForeignKey(
        "covenants.Covenant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="armies",
        help_text="Optional war covenant organizing this force.",
    )
    disbanded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this army was disbanded. Null means active.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    units = models.ManyToManyField(
        MilitaryUnit,
        through="ArmyMembership",
        related_name="armies",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_active(self) -> bool:
        """True when this army has not been disbanded."""
        return self.disbanded_at is None

    @property
    def active_units(self) -> models.QuerySet[MilitaryUnit]:
        """MilitaryUnits currently in this army (left_at is null)."""
        return self.units.filter(army_memberships__left_at__isnull=True)


class ArmyMembership(SharedMemoryModel):
    """A MilitaryUnit's membership in an Army.

    Active membership = ``left_at`` is null. A unit can leave an army without
    the army being disbanded. A unit can be in multiple armies simultaneously
    (e.g. a domain garrison that's also part of a campaign army).
    """

    army = models.ForeignKey(
        Army,
        on_delete=models.CASCADE,
        related_name="army_memberships",
    )
    military_unit = models.ForeignKey(
        MilitaryUnit,
        on_delete=models.PROTECT,
        related_name="army_memberships",
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this unit left the army. Null means active membership.",
    )

    class Meta:
        ordering = ["army", "joined_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["army", "military_unit"],
                condition=models.Q(left_at__isnull=True),
                name="unique_active_army_membership",
            )
        ]

    def __str__(self) -> str:
        status = "active" if self.left_at is None else "departed"
        return f"{self.military_unit.name} in {self.army.name} ({status})"
