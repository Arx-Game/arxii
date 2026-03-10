"""Models for the societies system.

This module contains models for:
- Society: Socio-political strata within a Realm with principle values
- OrganizationType: Templates defining rank titles for organization categories
- Organization: Groups within societies with principle overrides
- OrganizationMembership: Links guises to organizations with ranks
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

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import connection, models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
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

    The six standard types are:
    - noble_family: Traditional noble houses
    - commoner_family: Non-noble family structures
    - business: Commercial enterprises
    - guild: Professional associations
    - secret_society: Clandestine organizations
    - gang: Criminal organizations
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique identifier for this organization type (e.g., 'noble_family')",
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
    Each organization belongs to a society and has a type that determines
    its default rank structure.

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
        on_delete=models.CASCADE,
        related_name="organizations",
        help_text="The society this organization belongs to",
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

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.society.name})"

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
        """
        override_field = f"{principle_name}_override"
        override_value = getattr(self, override_field)
        if override_value is not None:
            return override_value
        return getattr(self.society, principle_name)

    def get_rank_title(self, rank: int) -> str:
        """
        Get the effective title for a rank.

        Returns the organization's override if set, otherwise returns the
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


class OrganizationMembership(models.Model):
    """
    Links a Guise (character identity) to an Organization with a rank.

    Memberships represent a character's involvement in an organization through
    their guise. Each guise can only have one membership per organization.

    Rank values:
    - 1: Leader/highest rank
    - 5: Lowest rank/contact

    Only default guises (is_default=True) or persistent guises (is_persistent=True)
    can hold organization memberships. Temporary disguises cannot join organizations.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
        help_text="The organization this membership belongs to",
    )
    guise = models.ForeignKey(
        "character_sheets.Guise",
        on_delete=models.CASCADE,
        related_name="organization_memberships",
        help_text="The guise (character identity) that holds this membership",
    )
    rank = models.IntegerField(
        default=RANK_MAX,
        validators=[MinValueValidator(RANK_MIN), MaxValueValidator(RANK_MAX)],
        help_text=f"Rank within the organization ({RANK_MIN}=leader, {RANK_MAX}=lowest)",
    )
    joined_date = models.DateTimeField(
        auto_now_add=True,
        help_text="When the guise joined this organization",
    )

    class Meta:
        verbose_name = "Organization Membership"
        verbose_name_plural = "Organization Memberships"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "guise"],
                name="unique_organization_guise_membership",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.guise.name} - {self.organization.name} (Rank {self.rank})"

    def clean(self) -> None:
        """
        Validate the membership.

        Ensures that only default or persistent guises can hold organization
        memberships. Temporary disguises cannot join organizations.
        """
        super().clean()

        if self.guise_id:
            # Check if guise is allowed to hold memberships
            # A guise must be either the default guise or a persistent guise
            if not self.guise.is_default and not self.guise.is_persistent:
                raise ValidationError(
                    {
                        "guise": (
                            "Only primary identities or persistent aliases can join organizations."
                        )
                    }
                )

    def save(self, *args, **kwargs):
        """Override save to run validation."""
        self.full_clean()
        super().save(*args, **kwargs)

    def get_title(self) -> str:
        """
        Get the title for this membership's rank from the organization.

        Returns:
            The title string for this member's rank within the organization.
        """
        return self.organization.get_rank_title(self.rank)


class SocietyReputation(models.Model):
    """
    Tracks a guise's reputation standing with a society.

    Reputation ranges from -1000 (Reviled) to +1000 (Revered). The numeric
    value is hidden from players; they see named tiers instead (e.g., "Favored",
    "Disliked").

    Only default guises (is_default=True) or persistent guises (is_persistent=True)
    can have society reputations. Temporary disguises cannot build reputation.
    """

    guise = models.ForeignKey(
        "character_sheets.Guise",
        on_delete=models.CASCADE,
        related_name="society_reputations",
        help_text="The guise (character identity) this reputation belongs to",
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
                fields=["guise", "society"],
                name="unique_guise_society_reputation",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.guise.name} - {self.society.name}: {self.get_tier().display_name}"

    def clean(self) -> None:
        """
        Validate the reputation.

        Ensures that only default or persistent guises can have society reputations.
        """
        super().clean()

        if self.guise_id:
            if not self.guise.is_default and not self.guise.is_persistent:
                raise ValidationError(
                    {
                        "guise": (
                            "Only primary identities or persistent aliases can have "
                            "society reputations."
                        )
                    }
                )

    def save(self, *args, **kwargs):
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


class OrganizationReputation(models.Model):
    """
    Tracks a guise's reputation standing with an organization.

    Reputation ranges from -1000 (Reviled) to +1000 (Revered). The numeric
    value is hidden from players; they see named tiers instead (e.g., "Favored",
    "Disliked").

    Only default guises (is_default=True) or persistent guises (is_persistent=True)
    can have organization reputations. Temporary disguises cannot build reputation.
    """

    guise = models.ForeignKey(
        "character_sheets.Guise",
        on_delete=models.CASCADE,
        related_name="organization_reputations",
        help_text="The guise (character identity) this reputation belongs to",
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
                fields=["guise", "organization"],
                name="unique_guise_organization_reputation",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.guise.name} - {self.organization.name}: {self.get_tier().display_name}"

    def clean(self) -> None:
        """
        Validate the reputation.

        Ensures that only default or persistent guises can have organization
        reputations.
        """
        super().clean()

        if self.guise_id:
            if not self.guise.is_default and not self.guise.is_persistent:
                raise ValidationError(
                    {
                        "guise": (
                            "Only primary identities or persistent aliases can have "
                            "organization reputations."
                        )
                    }
                )

    def save(self, *args, **kwargs):
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
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-friendly identifier",
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
        config, _created = cls.objects.get_or_create(pk=1)
        return config

    def __str__(self) -> str:
        return (
            f"SpreadingConfig(cap_multiplier={self.default_spread_multiplier}, "
            f"audience_factor={self.base_audience_factor})"
        )


class LegendEvent(models.Model):
    """
    A specific event that generated legend for participants.

    LegendEvent represents a notable occurrence (combat, story beat, discovery)
    that can award legend to one or more characters. Individual awards are
    tracked via LegendEntry instances linked back to this event.
    """

    title = models.CharField(
        max_length=200,
        help_text="Short name for the event",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what happened",
    )
    source_type = models.ForeignKey(
        LegendSourceType,
        on_delete=models.PROTECT,
        related_name="events",
        help_text="The category of this legend-generating event",
    )
    base_value = models.PositiveIntegerField(
        help_text="Base legend value awarded by this event",
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
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.title


class LegendEntry(models.Model):
    """
    A deed or accomplishment that earns legend for a guise.

    LegendEntry represents a notable achievement that a character has performed
    under a specific identity (guise). The entry has a base legend value that
    can be increased through spreading/embellishing the tale.

    Legend Calculation:
    - Entry total = base_value + sum of all spreads' value_added
    - Guise total = sum of all entries' totals
    - Character total (for Path advancement) = sum of all guises' totals
    """

    guise = models.ForeignKey(
        "character_sheets.Guise",
        on_delete=models.CASCADE,
        related_name="legend_entries",
        help_text="The guise (identity) that earned this legend",
    )
    title = models.CharField(
        max_length=200,
        help_text="Short name for the deed (e.g., 'Slew the Vampire Lord')",
    )
    description = models.TextField(
        blank=True,
        help_text="Player freeform writeup of how the deed went down",
    )
    base_value = models.PositiveIntegerField(
        default=0,
        help_text="Initial legend value from the deed itself",
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Legend Entry"
        verbose_name_plural = "Legend Entries"

    def __str__(self) -> str:
        return f"{self.guise.name}: {self.title}"

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


class LegendSpread(models.Model):
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
    spreader_guise = models.ForeignKey(
        "character_sheets.Guise",
        on_delete=models.CASCADE,
        related_name="legend_spreads",
        help_text="The guise (identity) that spread this legend",
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
        return f"{self.spreader_guise.name} spread: {self.legend_entry.title}"


class LegendDeedStory(models.Model):
    """
    A player-written account of a legendary deed.

    Each guise (via their author identity) can write one account per deed,
    providing their perspective on what happened.
    """

    deed = models.ForeignKey(
        LegendEntry,
        on_delete=models.CASCADE,
        related_name="deed_stories",
        help_text="The legend entry this story is about",
    )
    author = models.ForeignKey(
        "character_sheets.Guise",
        on_delete=models.CASCADE,
        related_name="legend_stories_written",
        help_text="The guise that wrote this account",
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


class CharacterLegendSummary(models.Model):
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


class GuiseLegendSummary(models.Model):
    """Read-only model backed by a PostgreSQL materialized view."""

    guise = models.OneToOneField(
        "character_sheets.Guise",
        on_delete=models.DO_NOTHING,
        primary_key=True,
        related_name="+",
    )
    guise_legend = models.IntegerField()

    class Meta:
        managed = False
        db_table = "societies_guiselegendsummary"


def refresh_legend_views() -> None:
    """Refresh both legend materialized views concurrently."""
    with connection.cursor() as cursor:
        cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY societies_characterlegendsummary")
        cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY societies_guiselegendsummary")
