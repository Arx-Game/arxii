"""Models for the societies system.

This module contains models for:
- Society: Socio-political strata within a Realm with principle values
- OrganizationType: Templates defining rank titles for organization categories
- Organization: Groups within societies with principle overrides
- OrganizationMembership: Links personas to organizations with ranks
- SocietyReputation: Reputation standing with a society
- OrganizationReputation: Reputation standing with an organization
- LegendSourceType: Categorization of what generates legend
- LegendEvent: A specific event that generated legend for participants
- LegendEntry: Deeds and accomplishments that earn legend
- LegendSpread: Instances of spreading/embellishing deeds
- LegendDeedStory: Player-written accounts of legendary deeds
- SpreadingConfig: Server-wide configuration for legend spreading

Note: Realm model is in the `realms` app, not here.
"""

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import connection, models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.societies.constants import (
    COMMON_KNOWLEDGE_MULTIPLIER,
    DeedKnowledgeSource,
    FameTier,
)
from world.societies.types import ReputationTier

# Validators for principle fields (-5 to +5 range)
PRINCIPLE_MIN = -5
PRINCIPLE_MAX = 5
principle_validators = [MinValueValidator(PRINCIPLE_MIN), MaxValueValidator(PRINCIPLE_MAX)]

# Rank constraints
RANK_MIN = 1
RANK_MAX = 5

# Reputation constraints
REPUTATION_MIN = -1000
REPUTATION_MAX = 1000
reputation_validators = [
    MinValueValidator(REPUTATION_MIN),
    MaxValueValidator(REPUTATION_MAX),
]


class Society(NaturalKeyMixin, SharedMemoryModel):
    """
    A socio-political stratum within a Realm.

    Societies represent distinct social groups with shared values and norms.
    Each society has six principle values on a -5 to +5 scale that define
    its cultural tendencies and moral compass.

    Principle Scales:
    - mercy: Ruthlessness (-5) to Compassion (+5)
    - method: Cunning (-5) to Honor (+5)
    - status: Ambition (-5) to Humility (+5)
    - change: Tradition (-5) to Progress (+5)
    - allegiance: Loyalty (-5) to Independence (+5)
    - power: Hierarchy (-5) to Equality (+5)
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    realm = models.ForeignKey(
        "realms.Realm",
        on_delete=models.CASCADE,
        related_name="societies",
    )
    enforcer_name = models.CharField(
        max_length=100,
        default="The Watch",
        help_text=(
            "Admin-editable flavor: who hunts the wanted in this society's "
            "dominion (heat surfaces render it — e.g. Luxen's 'The Honest'). "
            "Phrase it as a collective plural: '<name> have been looking …'."
        ),
    )

    # Principle fields - all on a -5 to +5 scale
    mercy = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Ruthlessness (-5) to Compassion (+5)",
    )
    method = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Cunning (-5) to Honor (+5)",
    )
    status = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Ambition (-5) to Humility (+5)",
    )
    change = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Tradition (-5) to Progress (+5)",
    )
    allegiance = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Loyalty (-5) to Independence (+5)",
    )
    power = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Hierarchy (-5) to Equality (+5)",
    )

    # #676 Phase A: how isolated this society's information network is.
    # Effective tier subtraction applied when computing a persona's perceived
    # fame tier from this society's perspective. 0 = fully connected (sees
    # all tiers as authored). -4 = very isolated (only World Famous personas
    # register at all, and they read as Normal multiplier). Admin-tunable
    # per society. See docs on the Renown system in issue #676.
    fame_perception_offset = models.IntegerField(
        default=0,
        validators=[MinValueValidator(-4), MaxValueValidator(0)],
        help_text=(
            "How isolated this society's news flow is. 0 = fully connected; "
            "-4 = very isolated (only World Famous personas register at all, "
            "and only at Normal multiplier). See Renown design (#676)."
        ),
    )
    current_fashion_style = models.ForeignKey(
        "items.FashionStyle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="societies_current",
        help_text="The fashion style currently in vogue in this society (#513).",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        verbose_name_plural = "societies"

    def __str__(self) -> str:
        return f"{self.name} ({self.realm.name})"


class OrganizationType(NaturalKeyMixin, SharedMemoryModel):
    """
    A type of organization with default rank titles.

    Organization types define the structure and naming conventions for
    organizations. Each type has five ranks with customizable default titles.

    Rows are created on-demand by the systems that need them (e.g.,
    `Covenant.save()` does `get_or_create(name="covenant", defaults=...)`).
    No fixture is committed — fixtures are gitignored in this repo per the
    seed-data convention. Staff customize rank titles via admin once a row
    exists.

    Typical kind names used elsewhere:
    - noble_family, commoner_family, business, guild, secret_society, gang
    - covenant (used by `Covenant.save()` auto-create)
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique identifier for this organization type (e.g., 'noble', 'covenant')",
    )

    # Default rank titles - can be overridden per organization
    rank_1_title = models.CharField(
        max_length=50,
        default="Leader",
        help_text="Default title for rank 1 (highest)",
    )
    rank_2_title = models.CharField(
        max_length=50,
        default="Officer",
        help_text="Default title for rank 2",
    )
    rank_3_title = models.CharField(
        max_length=50,
        default="Member",
        help_text="Default title for rank 3",
    )
    rank_4_title = models.CharField(
        max_length=50,
        default="Associate",
        help_text="Default title for rank 4",
    )
    rank_5_title = models.CharField(
        max_length=50,
        default="Contact",
        help_text="Default title for rank 5 (lowest)",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class Organization(NaturalKeyMixin, SharedMemoryModel):
    """
    A specific group or faction within a Society.

    Organizations are the primary groupings that characters can belong to.
    Each organization belongs to a society (optional for standalone orgs like
    covenants) and has a type that determines its default rank structure.

    Organizations can override:
    - Principle values (inherit from society if not set)
    - Rank titles (inherit from org_type if not set)
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="The organization's name",
    )
    description = models.TextField(
        blank=True,
        help_text="A description of the organization's purpose and history",
    )
    society = models.ForeignKey(
        Society,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="organizations",
        help_text=(
            "The society this organization belongs to. May be NULL for "
            "standalone organizations (e.g., covenants) that exist independently."
        ),
    )
    org_type = models.ForeignKey(
        OrganizationType,
        on_delete=models.PROTECT,
        related_name="organizations",
        help_text="The type of organization, which determines default rank titles",
    )

    # Principle overrides - if null, inherit from society
    mercy_override = models.IntegerField(
        null=True,
        blank=True,
        validators=principle_validators,
        help_text="Override for mercy principle (-5 to +5). If null, uses society's value.",
    )
    method_override = models.IntegerField(
        null=True,
        blank=True,
        validators=principle_validators,
        help_text="Override for method principle (-5 to +5). If null, uses society's value.",
    )
    status_override = models.IntegerField(
        null=True,
        blank=True,
        validators=principle_validators,
        help_text="Override for status principle (-5 to +5). If null, uses society's value.",
    )
    change_override = models.IntegerField(
        null=True,
        blank=True,
        validators=principle_validators,
        help_text="Override for change principle (-5 to +5). If null, uses society's value.",
    )
    allegiance_override = models.IntegerField(
        null=True,
        blank=True,
        validators=principle_validators,
        help_text=("Override for allegiance principle (-5 to +5). If null, uses society's value."),
    )
    power_override = models.IntegerField(
        null=True,
        blank=True,
        validators=principle_validators,
        help_text="Override for power principle (-5 to +5). If null, uses society's value.",
    )

    # Rank title overrides - if blank, inherit from org_type
    rank_1_title_override = models.CharField(
        max_length=50,
        blank=True,
        help_text="Override for rank 1 title. If blank, uses org_type's default.",
    )
    rank_2_title_override = models.CharField(
        max_length=50,
        blank=True,
        help_text="Override for rank 2 title. If blank, uses org_type's default.",
    )
    rank_3_title_override = models.CharField(
        max_length=50,
        blank=True,
        help_text="Override for rank 3 title. If blank, uses org_type's default.",
    )
    rank_4_title_override = models.CharField(
        max_length=50,
        blank=True,
        help_text="Override for rank 4 title. If blank, uses org_type's default.",
    )
    rank_5_title_override = models.CharField(
        max_length=50,
        blank=True,
        help_text="Override for rank 5 title. If blank, uses org_type's default.",
    )

    # #676 Phase A: Renown system org prestige stores. base_prestige is
    # admin-authored and permanent; accumulated_* are event-fed from member
    # deeds and decay (cron task in tasks.py). accumulated_legend is
    # permanent and only populated for covenant-backed orgs (Org.covenant
    # OneToOne reverse exists) — see #676 spec for the body-flow rule.
    base_prestige = models.BigIntegerField(
        default=0,
        help_text=(
            "Admin-set permanent prestige floor for this organization. "
            "Never decays; never event-modified. Quarterly accounting may "
            "uplift base from accumulated, but that's a separate operation."
        ),
    )
    accumulated_prestige = models.BigIntegerField(
        default=0,
        help_text=(
            "Event-fed prestige accumulation from member deeds (10% of any "
            "member persona's deed prestige). Decays at a high rate per IC "
            "day via the renown decay cron."
        ),
    )
    accumulated_fame = models.BigIntegerField(
        default=0,
        help_text=(
            "Event-fed fame buffer for this organization, from member deed "
            "fame gains. Decays fast like persona fame."
        ),
    )
    accumulated_legend = models.BigIntegerField(
        default=0,
        help_text=(
            "Event-fed legend accumulation, COVENANTS ONLY. Body-flow rule: "
            "any member-body's legend gain credits 10% here regardless of "
            "which persona did the deed. Permanent — never decays. Used as "
            "a ritual-availability gate (separate magic design pass)."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        society_label = self.society.name if self.society else "standalone"
        return f"{self.name} ({society_label})"

    def get_effective_principle(self, principle_name: str) -> int:
        """
        Get the effective value for a principle.

        Returns the organization's override if set, otherwise returns the
        society's value for that principle.

        Args:
            principle_name: One of 'mercy', 'method', 'status', 'change',
                          'allegiance', or 'power'

        Returns:
            The effective principle value (-5 to +5)

        Raises:
            AttributeError: If principle_name is not a valid principle
            ValueError: If society is None and no override is set for the principle
        """
        override_field = f"{principle_name}_override"
        override_value = getattr(self, override_field)
        if override_value is not None:
            return override_value
        if self.society is None:
            msg = (
                f"Cannot resolve principle {principle_name!r} for standalone "
                f"organization {self.name!r}: no society and no override set."
            )
            raise ValueError(msg)
        return getattr(self.society, principle_name)

    def get_rank_title(self, rank: int) -> str:
        """Get the effective title for a rank.

        Returns the organization's override if set; otherwise returns the
        org_type's default title for that rank.

        Args:
            rank: The rank number (1-5, where 1 is highest)

        Returns:
            The effective title for that rank

        Raises:
            ValueError: If rank is not 1-5
        """
        if rank < RANK_MIN or rank > RANK_MAX:
            msg = f"Rank must be {RANK_MIN}-{RANK_MAX}, got {rank}"
            raise ValueError(msg)

        override_field = f"rank_{rank}_title_override"
        override_value = getattr(self, override_field)
        if override_value:
            return override_value

        default_field = f"rank_{rank}_title"
        return getattr(self.org_type, default_field)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Create a default five-rank ladder on first save for generic orgs."""
        super().save(*args, **kwargs)
        if self.org_type and self.org_type.name == "covenant":  # noqa: STRING_LITERAL
            return
        if not self.ranks.exists():
            from world.societies.membership_services import (  # noqa: PLC0415
                ensure_default_rank_ladder,
            )

            ensure_default_rank_ladder(self)


class OrganizationRank(SharedMemoryModel):
    """A single rung on an organization's five-tier rank ladder.

    Tier 1 is the highest authority; tier 5 is the lowest. Capability flags
    decide which members can invite, kick, or manage ranks.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="ranks",
        help_text="The organization this rank belongs to",
    )
    name = models.CharField(
        max_length=60,
        help_text="Diegetic name for this rung (e.g., Guildmaster, Captain)",
    )
    tier = models.PositiveIntegerField(
        help_text="Authority tier (1 highest, 5 lowest)",
    )
    can_invite = models.BooleanField(
        default=False,
        help_text="Members at this rank can invite others to the organization",
    )
    can_kick = models.BooleanField(
        default=False,
        help_text="Members at this rank can expel lower-ranked members",
    )
    can_manage_ranks = models.BooleanField(
        default=False,
        help_text="Members at this rank can promote/demote others",
    )

    class Meta:
        ordering = ["tier"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "tier"],
                name="unique_org_rank_tier",
            ),
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="unique_org_rank_name",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} (Tier {self.tier})"


class OrganizationMembershipOffer(SharedMemoryModel):
    """A pending or resolved invitation or application to join an organization.

    INVITE offers are directed at a specific persona (``to_persona``).
    APPLICATION offers are directed at the organization by an applicant
    (``from_persona``) and have no ``to_persona``.
    """

    class Kind(models.TextChoices):
        INVITE = "invite", "Invite"
        APPLICATION = "application", "Application"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="membership_offers",
    )
    from_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="sent_org_membership_offers",
    )
    to_persona = models.ForeignKey(
        "scenes.Persona",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="received_org_membership_offers",
    )
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    message = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "to_persona"],
                condition=models.Q(
                    status="pending",
                    kind="invite",
                    to_persona__isnull=False,
                ),
                name="unique_pending_org_invite_per_target",
            ),
            models.UniqueConstraint(
                fields=["organization", "from_persona"],
                condition=models.Q(
                    status="pending",
                    kind="application",
                ),
                name="unique_pending_org_application_per_applicant",
            ),
        ]

    def __str__(self) -> str:
        target = self.to_persona or self.from_persona
        return f"{self.kind} to {self.organization.name} for {target}"


class OrganizationMembership(SharedMemoryModel):
    """Links a Persona to an Organization with a rank rung.

    Active memberships have ``left_at IS NULL`` and ``exiled_at IS NULL``.
    A voluntary departure sets ``left_at``; a forced removal sets both
    ``left_at`` and ``exiled_at``.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
        help_text="The organization this membership belongs to",
    )
    persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="organization_memberships",
        help_text="The persona (character identity) that holds this membership",
    )
    rank = models.ForeignKey(
        OrganizationRank,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="memberships",
        help_text="Rank rung held within this organization",
    )
    joined_date = models.DateTimeField(
        auto_now_add=True,
        help_text="When the persona joined this organization",
    )
    left_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the persona voluntarily left the organization",
    )
    exiled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the persona was forcibly removed from the organization",
    )

    class Meta:
        verbose_name = "Organization Membership"
        verbose_name_plural = "Organization Memberships"
        ordering = ["organization", "rank__tier", "persona__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "persona"],
                condition=models.Q(
                    left_at__isnull=True,
                    exiled_at__isnull=True,
                ),
                name="unique_active_org_membership",
            ),
        ]

    def __str__(self) -> str:
        if self.rank_id:
            return (
                f"{self.persona.name} - {self.organization.name} "
                f"(Rank {self.rank.tier} - {self.rank.name})"
            )
        return f"{self.persona.name} - {self.organization.name} (No rank)"

    def clean(self) -> None:
        """Validate the membership."""
        super().clean()

        if self.persona_id and not self.persona.is_established_or_primary:
            raise ValidationError(
                {
                    "persona": (
                        "Only primary identities or established personas can join organizations."
                    )
                }
            )

        if self.rank_id and self.rank.organization_id != self.organization_id:
            raise ValidationError({"rank": "Rank does not belong to this organization."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Override save to run validation."""
        self.full_clean()
        super().save(*args, **kwargs)

    def get_title(self) -> str:
        """Return the effective title for this membership's rank rung."""
        if self.rank is None:
            return ""
        return self.organization.get_rank_title(self.rank.tier)


class SocietyReputation(SharedMemoryModel):
    """
    Tracks a persona's reputation standing with a society.

    Reputation ranges from -1000 (Reviled) to +1000 (Revered). The numeric
    value is hidden from players; they see named tiers instead (e.g., "Favored",
    "Disliked").

    Only primary or established personas can have society reputations.
    Temporary disguises cannot build reputation.
    """

    persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="society_reputations",
        help_text="The persona (character identity) this reputation belongs to",
    )
    society = models.ForeignKey(
        Society,
        on_delete=models.CASCADE,
        related_name="reputations",
        help_text="The society this reputation is with",
    )
    value = models.IntegerField(
        default=0,
        validators=reputation_validators,
        help_text=f"Reputation value ({REPUTATION_MIN} to {REPUTATION_MAX})",
    )

    class Meta:
        verbose_name = "Society Reputation"
        verbose_name_plural = "Society Reputations"
        constraints = [
            models.UniqueConstraint(
                fields=["persona", "society"],
                name="unique_persona_society_reputation",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.persona.name} - {self.society.name}: {self.get_tier().display_name}"

    def clean(self) -> None:
        """
        Validate the reputation.

        Ensures that only primary or established personas can have society reputations.
        """
        super().clean()

        if self.persona_id:
            if not self.persona.is_established_or_primary:
                raise ValidationError(
                    {
                        "persona": (
                            "Only primary identities or established personas can have "
                            "society reputations."
                        )
                    }
                )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Override save to run validation."""
        self.full_clean()
        super().save(*args, **kwargs)

    def get_tier(self) -> ReputationTier:
        """
        Get the reputation tier for the current value.

        Returns:
            The ReputationTier enum member corresponding to the current value.
        """
        return ReputationTier.from_value(self.value)


class OrganizationReputation(SharedMemoryModel):
    """
    Tracks a persona's reputation standing with an organization.

    Reputation ranges from -1000 (Reviled) to +1000 (Revered). The numeric
    value is hidden from players; they see named tiers instead (e.g., "Favored",
    "Disliked").

    Only primary or established personas can have organization reputations.
    Temporary disguises cannot build reputation.
    """

    persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="organization_reputations",
        help_text="The persona (character identity) this reputation belongs to",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="reputations",
        help_text="The organization this reputation is with",
    )
    value = models.IntegerField(
        default=0,
        validators=reputation_validators,
        help_text=f"Reputation value ({REPUTATION_MIN} to {REPUTATION_MAX})",
    )

    class Meta:
        verbose_name = "Organization Reputation"
        verbose_name_plural = "Organization Reputations"
        constraints = [
            models.UniqueConstraint(
                fields=["persona", "organization"],
                name="unique_persona_organization_reputation",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.persona.name} - {self.organization.name}: {self.get_tier().display_name}"

    def clean(self) -> None:
        """
        Validate the reputation.

        Ensures that only primary or established personas can have organization
        reputations.
        """
        super().clean()

        if self.persona_id:
            if not self.persona.is_established_or_primary:
                raise ValidationError(
                    {
                        "persona": (
                            "Only primary identities or established personas can have "
                            "organization reputations."
                        )
                    }
                )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Override save to run validation."""
        self.full_clean()
        super().save(*args, **kwargs)

    def get_tier(self) -> ReputationTier:
        """
        Get the reputation tier for the current value.

        Returns:
            The ReputationTier enum member corresponding to the current value.
        """
        return ReputationTier.from_value(self.value)


class LegendSourceType(NaturalKeyMixin, SharedMemoryModel):
    """
    Categorization of what generates legend.

    LegendSourceType defines the different categories of activities or events
    that can generate legend for characters (e.g., combat, story completion,
    discoveries).
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique name for this legend source type",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this source type represents",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order for display in lists (lower = first)",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this source type is currently available",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class SpreadingConfig(SharedMemoryModel):
    """
    Server-wide configuration for legend spreading mechanics.

    This is a singleton model (pk=1) that stores global configuration
    for how legend spreads work across the game.
    """

    objects = ArxSharedMemoryManager()

    default_spread_multiplier = models.PositiveIntegerField(
        default=9,
        help_text="Default spread multiplier for new deeds. Total legend can reach "
        "base_value * (1 + multiplier). With default 9, a deed worth 10 can reach 100.",
    )
    base_audience_factor = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("1.0"),
        help_text="Base factor applied to audience calculations for spreading",
    )
    spread_assist_fraction = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("0.10"),
        help_text=(
            "Bonus spread per PC acclaim of a telling (#915), as a fraction of "
            "the original telling's value. PC assists are deliberately minor; "
            "the NPC traffic band stays the primary spread vector."
        ),
    )
    spread_assist_per_scene_cap = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Hard cap on the total spread-assist bonus from one telling (#915). "
            "0 = no separate cap (still clamped by the deed's remaining capacity)."
        ),
    )

    class Meta:
        verbose_name = "Spreading Configuration"
        verbose_name_plural = "Spreading Configuration"

    @classmethod
    def get_active_config(cls) -> "SpreadingConfig":
        """
        Get or create the singleton spreading configuration.

        Returns:
            The active SpreadingConfig instance (pk=1).
        """
        config = cls.objects.cached_singleton()
        if config is None:
            config, _created = cls.objects.get_or_create(pk=1)
        return config

    def __str__(self) -> str:
        return (
            f"SpreadingConfig(cap_multiplier={self.default_spread_multiplier}, "
            f"audience_factor={self.base_audience_factor})"
        )


class SpreadAssistTarget(SharedMemoryModel):
    """Links a SPREAD_ASSIST reaction window to the deed it can boost (#915).

    Written when a telling opens its reaction window — the generic
    ReactionWindow can't carry kind-specific data, so this is the per-kind
    "settlement target" (the SceneEntryEndorsement pattern). At scene close the
    SPREAD_ASSIST handler reads it to size the bonus spread (a fraction of
    ``original_value`` per acclaim) and reward the acclaiming reactors.
    """

    window = models.OneToOneField(
        "scenes.ReactionWindow",
        on_delete=models.CASCADE,
        related_name="spread_assist_target",
    )
    legend_entry = models.ForeignKey(
        "societies.LegendEntry",
        on_delete=models.CASCADE,
        related_name="spread_assist_targets",
        help_text="The deed the telling spread; acclaim adds a minor bonus to it.",
    )
    original_value = models.PositiveIntegerField(
        help_text="The telling's own spread value; the bonus is a fraction of this.",
    )

    def __str__(self) -> str:
        return f"SpreadAssistTarget(window={self.window_id}, deed={self.legend_entry_id})"


class AbstractLegendRecord(models.Model):
    """Abstract base for shared fields between LegendEvent and LegendEntry."""

    title = models.CharField(
        max_length=200,
        help_text="Short name for this legend record",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what happened",
    )
    base_value = models.PositiveIntegerField(
        default=0,
        help_text="Base legend value",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class LegendEvent(AbstractLegendRecord):
    """
    A specific event that generated legend for participants.

    LegendEvent represents a notable occurrence (combat, story beat, discovery)
    that can award legend to one or more characters. Individual awards are
    tracked via LegendEntry instances linked back to this event.
    """

    source_type = models.ForeignKey(
        LegendSourceType,
        on_delete=models.PROTECT,
        related_name="events",
        help_text="The category of this legend-generating event",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="legend_events",
        help_text="The scene where this event occurred, if any",
    )
    story = models.ForeignKey(
        "stories.Story",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="legend_events",
        help_text="The story this event is part of, if any",
    )
    created_by = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_legend_events",
        help_text="The account that created this event",
    )

    def __str__(self) -> str:
        return self.title


class LegendEntry(AbstractLegendRecord):
    """
    A deed or accomplishment that earns legend for a persona.

    LegendEntry represents a notable achievement that a character has performed
    under a specific identity (persona). The entry has a base legend value that
    can be increased through spreading/embellishing the tale.

    Legend Calculation:
    - Entry total = base_value + sum of all spreads' value_added
    - Persona total = sum of all entries' totals
    - Character total (for Path advancement) = sum of all personas' totals
    """

    persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="legend_entries",
        help_text="The persona (identity) that earned this legend",
    )
    source_note = models.TextField(
        blank=True,
        help_text="Freeform placeholder for source (until mission/event models exist)",
    )
    location_note = models.TextField(
        blank=True,
        help_text="Freeform placeholder for location (until grid exists)",
    )
    event = models.ForeignKey(
        LegendEvent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deeds",
        help_text="The legend event that generated this entry, if any",
    )
    source_type = models.ForeignKey(
        LegendSourceType,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="deeds",
        help_text="The category of this deed's source",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="legend_entries",
        help_text="The scene where this deed occurred, if any",
    )
    story = models.ForeignKey(
        "stories.Story",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="legend_entries",
        help_text="The story this deed is part of, if any",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this entry contributes to legend totals",
    )
    updated_at = models.DateTimeField(auto_now=True)
    spread_multiplier = models.PositiveIntegerField(
        default=9,
        help_text="How many times the base_value can be added via spreading. "
        "Total legend = base_value + up to (base_value * spread_multiplier).",
    )
    societies_aware = models.ManyToManyField(
        Society,
        blank=True,
        related_name="known_legend_entries",
        help_text="Which societies know about this deed",
    )
    # #737: Archetypes attached at fire-time so spread (and other
    # awareness-extension paths) can re-fire archetype-dot-product
    # reputation deltas for societies that become newly-aware later.
    # Without this M2M, the archetype vector is lost after the original
    # fire_renown_award call and spread can only widen awareness, not
    # propagate the moral reading the original deed carried.
    archetypes = models.ManyToManyField(
        "societies.PhilosophicalArchetype",
        blank=True,
        related_name="legend_entries",
        help_text=(
            "Philosophical archetypes attached to this deed at fire time. "
            "Used by spread-awareness extension to re-fire per-society "
            "reputation deltas when new societies become aware."
        ),
    )

    class Meta:
        verbose_name = "Legend Entry"
        verbose_name_plural = "Legend Entries"

    def __str__(self) -> str:
        return f"{self.persona.name}: {self.title}"

    @property
    def max_spread(self) -> int:
        """Calculate the maximum total spread value for this entry."""
        return self.base_value * self.spread_multiplier

    @property
    def spread_value(self) -> int:
        """Calculate the current total spread value from all spreads."""
        result = self.spreads.aggregate(total=models.Sum("value_added"))["total"]
        return result or 0

    @property
    def remaining_spread_capacity(self) -> int:
        """Calculate how much more spread value can be added."""
        return max(0, self.max_spread - self.spread_value)

    def get_total_value(self) -> int:
        """
        Calculate the total legend value for this entry.

        Returns 0 if the entry is inactive. Otherwise returns the base_value
        plus the sum of all value_added from spreads.

        Returns:
            Total legend value (base + all spreads), or 0 if inactive.
        """
        if not self.is_active:
            return 0
        return self.base_value + self.spread_value

    @property
    def is_common_knowledge(self) -> bool:
        """A tale that has grown to 5× its base belongs to everyone (#902).

        Computed, never stored — the gate moves with the spreads. Inactive
        deeds are never common knowledge (total is 0), nor are zero-base
        deeds (nothing to multiply).
        """
        if self.base_value <= 0:
            return False
        return self.get_total_value() >= COMMON_KNOWLEDGE_MULTIPLIER * self.base_value


class LegendSpread(SharedMemoryModel):
    """
    An instance of spreading or embellishing a legendary deed.

    LegendSpread represents when someone tells or retells a legend entry,
    potentially adding to its legend value through embellishment. Each spread
    tracks who spread it, how, and which societies heard this version.
    """

    legend_entry = models.ForeignKey(
        LegendEntry,
        on_delete=models.CASCADE,
        related_name="spreads",
        help_text="The legend entry being spread",
    )
    spreader_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="legend_spreads",
        help_text="The persona (identity) that spread this legend",
    )
    value_added = models.PositiveIntegerField(
        default=0,
        help_text="How much legend this spread contributed",
    )
    description = models.TextField(
        blank=True,
        help_text="The embellished version / how they told it",
    )
    method = models.TextField(
        blank=True,
        help_text="How it was spread (e.g., bard song, tavern gossip, pamphlet)",
    )
    skill = models.ForeignKey(
        "skills.Skill",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="legend_spreads",
        help_text="The skill used for this spread, if any",
    )
    audience_factor = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("1.0"),
        help_text="Multiplier based on audience size/quality",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="legend_spreads",
        help_text="The scene where this spread occurred, if any",
    )
    societies_reached = models.ManyToManyField(
        Society,
        blank=True,
        related_name="heard_legend_spreads",
        help_text="Which societies heard this version",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Legend Spread"
        verbose_name_plural = "Legend Spreads"

    def __str__(self) -> str:
        return f"{self.spreader_persona.name} spread: {self.legend_entry.title}"


class LegendDeedStory(SharedMemoryModel):
    """
    A player-written account of a legendary deed.

    Each persona (via their author identity) can write one account per deed,
    providing their perspective on what happened.
    """

    deed = models.ForeignKey(
        LegendEntry,
        on_delete=models.CASCADE,
        related_name="deed_stories",
        help_text="The legend entry this story is about",
    )
    author = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="legend_stories_written",
        help_text="The persona that wrote this account",
    )
    text = models.TextField(
        help_text="The player-written account of the deed",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Legend Deed Story"
        verbose_name_plural = "Legend Deed Stories"
        constraints = [
            models.UniqueConstraint(
                fields=["deed", "author"],
                name="unique_deed_story_per_author",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.author.name}'s account of: {self.deed.title}"


class PersonaDeedKnowledge(SharedMemoryModel):
    """One persona's IC knowledge of one deed (#902).

    Rows exist for the witness and heard-told vectors; the doer needs no row
    and common knowledge is computed (``LegendEntry.is_common_knowledge``).
    One row per (persona, deed) — the first vector to arrive wins; ``source``
    is provenance for the fiction, never a permission tier.
    """

    persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="deed_knowledge",
        help_text="The persona that knows of the deed",
    )
    deed = models.ForeignKey(
        LegendEntry,
        on_delete=models.CASCADE,
        related_name="knowledge_rows",
        help_text="The deed known of",
    )
    source = models.CharField(
        max_length=20,
        choices=DeedKnowledgeSource.choices,
        help_text="How the knowledge arrived (witnessed / heard the tale told)",
    )
    learned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Persona Deed Knowledge"
        verbose_name_plural = "Persona Deed Knowledge"
        constraints = [
            models.UniqueConstraint(
                fields=["persona", "deed"],
                name="unique_deed_knowledge_per_persona",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.persona.name} knows of: {self.deed.title} ({self.source})"


class CharacterLegendSummary(SharedMemoryModel):
    """Read-only model backed by a PostgreSQL materialized view."""

    character = models.OneToOneField(
        "objects.ObjectDB",
        on_delete=models.DO_NOTHING,
        primary_key=True,
        related_name="+",
    )
    personal_legend = models.IntegerField()

    class Meta:
        managed = False
        db_table = "societies_characterlegendsummary"


class PersonaLegendSummary(SharedMemoryModel):
    """Read-only model backed by a PostgreSQL materialized view."""

    persona = models.OneToOneField(
        "scenes.Persona",
        on_delete=models.DO_NOTHING,
        primary_key=True,
        related_name="+",
    )
    persona_legend = models.IntegerField()

    class Meta:
        managed = False
        db_table = "societies_personalegendsummary"


class RankingDisplay(SharedMemoryModel):
    """#676 Phase I — Diegetic ranking display: an in-world IC object
    that shows a top-N leaderboard when interacted with.

    Heralds at major society meeting places show society prestige
    rankings; Academy displays show legend rankings. Per-society
    rankings are gated by the viewer's society membership (handled at
    interact time, not here).

    The ``display_object`` is the Evennia ObjectDB the player interacts
    with. ``ranking_type`` discriminates the data source. ``scope_target``
    is the FK to the scope (which society for SOCIETY_PRESTIGE rankings,
    null for global Legend rankings).
    """

    class RankingType(models.TextChoices):
        SOCIETY_PRESTIGE = "society_prestige", "Society Prestige"
        ACADEMY_LEGEND = "academy_legend", "Academy Legend"
        FASHION = "society_fashion", "Society Fashion"

    display_object = models.OneToOneField(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="ranking_display",
        help_text=(
            "The Evennia object (a herald, plaque, board) players "
            "interact with to view the ranking."
        ),
    )
    ranking_type = models.CharField(
        max_length=30,
        choices=RankingType.choices,
        db_index=True,
    )
    scope_society = models.ForeignKey(
        "societies.Society",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ranking_displays",
        help_text=(
            "Society this display is scoped to. Required for "
            "SOCIETY_PRESTIGE; null for ACADEMY_LEGEND (global)."
        ),
    )
    top_n = models.PositiveIntegerField(
        default=10,
        help_text="How many entries to show.",
    )

    class Meta:
        constraints = [
            # SOCIETY_PRESTIGE and FASHION rankings must scope to a specific
            # society; ACADEMY_LEGEND rankings are global (society must be null).
            models.CheckConstraint(
                check=(
                    models.Q(
                        ranking_type="society_prestige",
                        scope_society__isnull=False,
                    )
                    | models.Q(
                        ranking_type="academy_legend",
                        scope_society__isnull=True,
                    )
                    | models.Q(
                        ranking_type="society_fashion",
                        scope_society__isnull=False,
                    )
                ),
                name="societies_ranking_display_scope_matches_type",
            ),
        ]

    def __str__(self) -> str:
        scope = self.scope_society.name if self.scope_society else "global"
        return f"{self.get_ranking_type_display()} @ {scope}"


class RankingBandLabel(SharedMemoryModel):
    """#761 — qualitative label for a band of ranking positions.

    The diegetic boards never show raw numbers (hidden-mechanics rule);
    instead each rank position falls into an authored band ("among the
    most renowned", "a rising name"). Per-society rows let cultures speak
    rank differently; ``society=null`` rows are the global/default set,
    used by ACADEMY_LEGEND boards and as the fallback when a society has
    authored none. Admin-editable per the flavor-text rule; with no
    authored bands a board renders ordered names with no label at all.
    """

    society = models.ForeignKey(
        Society,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ranking_band_labels",
        help_text="Null = the global/default label set (Academy boards + fallback).",
    )
    rank_min = models.PositiveSmallIntegerField(
        help_text="First rank position (1-based, inclusive) this label covers.",
    )
    rank_max = models.PositiveSmallIntegerField(
        help_text="Last rank position (inclusive) this label covers.",
    )
    label = models.CharField(
        max_length=200,
        help_text="The qualitative phrase rendered beside names in this band.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(rank_min__lte=models.F("rank_max")),
                name="societies_band_label_min_lte_max",
            ),
        ]

    def __str__(self) -> str:
        scope = self.society.name if self.society_id else "global"
        return f"[{scope}] ranks {self.rank_min}-{self.rank_max}: {self.label[:40]}"


class FameReactionLine(SharedMemoryModel):
    """#881 — an authored room-entry reaction to a notable arrival.

    Per-room, per-society, entirely optional: the noble meeting hall
    reacts differently from the salon, and unauthored rooms say nothing.
    Fires when a character whose perceived fame tier meets
    ``min_fame_tier`` enters ``room`` — bystanders receive
    ``bystander_body``; the arriver receives ``arriver_body`` (the
    actor/audience split). A society-voiced line perceives the arriver's
    tier through that society's ``fame_perception_offset``; ``society``
    null reads the raw tier. Admin-editable per the flavor-text rule.
    """

    room = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        on_delete=models.CASCADE,
        related_name="fame_reaction_lines",
    )
    society = models.ForeignKey(
        Society,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="fame_reaction_lines",
        help_text=(
            "The society whose voice this room speaks with — its "
            "fame_perception_offset filters how famous the arriver reads. "
            "Null = raw fame tier."
        ),
    )
    min_fame_tier = models.CharField(
        max_length=20,
        choices=FameTier.choices,
        default=FameTier.TALKED_ABOUT,
        help_text="Minimum perceived fame tier of the arriver for this line to fire.",
    )
    bystander_body = models.TextField(
        blank=True,
        help_text="What the room's other occupants see when the line fires.",
    )
    arriver_body = models.TextField(
        blank=True,
        help_text="What the arriving character themselves sees.",
    )
    weight = models.PositiveIntegerField(
        default=1,
        help_text="Relative draw weight among this room's eligible lines.",
    )
    is_active = models.BooleanField(default=True)

    def clean(self) -> None:
        super().clean()
        if not self.bystander_body and not self.arriver_body:
            raise ValidationError(
                {"bystander_body": "Author at least one of bystander_body / arriver_body."}
            )

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        voice = self.society.name if self.society_id else "no-society"
        return f"FameReactionLine(room={self.room_id}, {voice}, >={self.min_fame_tier})"


class FameReactionCooldown(SharedMemoryModel):
    """#881 — per-(persona, room) re-fire throttle for fame reactions.

    Mirrors ``missions.MissionGiverCooldown``: without it, pacing in and
    out of an authored room spams every occupant. One row per pair,
    upserted on fire.
    """

    persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="fame_reaction_cooldowns",
    )
    room = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        on_delete=models.CASCADE,
        related_name="fame_reaction_cooldowns",
    )
    available_at = models.DateTimeField(
        help_text="Reactions to this persona in this room re-fire after this time.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["persona", "room"],
                name="unique_fame_reaction_cooldown_pair",
            ),
        ]

    def __str__(self) -> str:
        return f"FameReactionCooldown(persona={self.persona_id}, room={self.room_id})"


class CovenantLegendCredit(SharedMemoryModel):
    """Per-deed-per-covenant credit row. Snapshotted at LegendEntry creation
    from the persona's currently-engaged covenants. The covenant's total
    derives by summing base_value + spreads across these rows.
    """

    entry = models.ForeignKey(
        LegendEntry,
        on_delete=models.CASCADE,
        related_name="covenant_credits",
    )
    covenant = models.ForeignKey(
        "covenants.Covenant",
        on_delete=models.PROTECT,
        related_name="legend_credits",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entry", "covenant"],
                name="societies_credit_unique_per_entry_covenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.entry} → {self.covenant}"


class CovenantLegendSummary(SharedMemoryModel):
    """Materialized view of covenant legend totals (base + spreads).

    DO NOT WRITE TO THIS MODEL DIRECTLY. Backed by SQL view refreshed by
    refresh_legend_views().
    """

    covenant = models.OneToOneField(
        "covenants.Covenant",
        on_delete=models.DO_NOTHING,
        primary_key=True,
        db_column="covenant_id",
        related_name="legend_summary",
    )
    legend_total = models.PositiveBigIntegerField()

    class Meta:
        managed = False
        db_table = "societies_covenantlegendsummary"


def refresh_legend_views() -> None:
    """Refresh all legend materialized views concurrently."""
    with connection.cursor() as cursor:
        cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY societies_characterlegendsummary")
        cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY societies_personalegendsummary")
        cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY societies_covenantlegendsummary")


# ---------------------------------------------------------------------------
# Renown system (#676 Phase B)
# ---------------------------------------------------------------------------


class PhilosophicalArchetype(NaturalKeyMixin, SharedMemoryModel):
    """Tag a Renown event with one or more archetypes; each contributes a
    six-axis principle vector that dot-products against affected societies'
    own principle values to produce the reputation delta.

    Admin-authored library — Heroic, Treacherous, Lawful, Reformist, Pious,
    Mercantile, etc. Multiple archetypes on an event sum their vectors.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    # Six principle deltas mirror Society.{mercy, method, status, change,
    # allegiance, power}. Typical authored range is -2..+2; ±5 is allowed
    # for rare extreme archetypes but most archetypes should be subtler.
    mercy_delta = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Compassion (+) ↔ Ruthlessness (-) axis contribution.",
    )
    method_delta = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Honor (+) ↔ Cunning (-) axis contribution.",
    )
    status_delta = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Humility (+) ↔ Ambition (-) axis contribution.",
    )
    change_delta = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Progress (+) ↔ Tradition (-) axis contribution.",
    )
    allegiance_delta = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Independence (+) ↔ Loyalty (-) axis contribution.",
    )
    power_delta = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Equality (+) ↔ Hierarchy (-) axis contribution.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name
