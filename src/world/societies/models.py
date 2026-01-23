"""Models for the societies system.

This module contains models for:
- Realm: Nations/kingdoms that serve as containers for societies
- Society: Socio-political strata within a Realm with principle values
- OrganizationType: Templates defining rank titles for organization categories
- Organization: Groups within societies with principle overrides
- OrganizationMembership: Links guises to organizations with ranks
- SocietyReputation: Reputation standing with a society
- OrganizationReputation: Reputation standing with an organization
- LegendEntry: Deeds and accomplishments that earn legend
- LegendSpread: Instances of spreading/embellishing deeds
"""

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
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


class Realm(NaturalKeyMixin, SharedMemoryModel):
    """
    A nation or kingdom that contains societies.

    Realms are the top-level political containers in the game world.
    Each realm can have multiple societies representing different
    social strata or political factions.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


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
        Realm,
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
    base_value = models.IntegerField(
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

    def get_total_value(self) -> int:
        """
        Calculate the total legend value for this entry.

        Returns the base_value plus the sum of all value_added from spreads.

        Returns:
            Total legend value (base + all spreads).
        """
        spread_total = self.spreads.aggregate(total=models.Sum("value_added"))["total"]
        return self.base_value + (spread_total or 0)


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
    value_added = models.IntegerField(
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
