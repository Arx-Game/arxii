"""
Character Creation models.

Models for the staged character creation flow:
- StartingArea: Selectable origin locations that gate heritage options
- SpecialHeritage: Special origin types (Sleeper, Misbegotten) that bypass normal family
- CharacterDraft: In-progress character creation state
"""

from datetime import timedelta

from django.db import models
from django.utils import timezone
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel


class StartingArea(SharedMemoryModel):
    """
    A starting location/city that players can select in character creation.

    Each area gates which heritage options, species, and families are available.
    Maps to an Evennia room for character starting location.

    Note: Rooms may be None during early testing before grid is built.
    """

    class AccessLevel(models.TextChoices):
        ALL = "all", "All Players"
        TRUST_REQUIRED = "trust_required", "Trust Required"
        STAFF_ONLY = "staff_only", "Staff Only"

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Display name of the starting area (e.g., 'Arx')",
    )
    description = models.TextField(
        help_text="Rich description shown on hover/click in character creation",
    )
    crest_image = models.URLField(
        blank=True,
        null=True,
        help_text="Cloudinary URL for crest/flag image. Leave blank for gradient placeholder.",
    )
    default_starting_room = models.ForeignKey(
        ObjectDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="starting_area_default",
        help_text="Default Evennia room where characters from this area start. "
        "Can be None during early testing.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this area can be selected in character creation",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order in selection UI (lower = first)",
    )
    access_level = models.CharField(
        max_length=20,
        choices=AccessLevel.choices,
        default=AccessLevel.ALL,
        help_text="Who can select this area in character creation",
    )
    minimum_trust = models.IntegerField(
        default=0,
        help_text="Minimum trust required when access_level is 'trust_required'",
    )

    # M2M to special heritages available in this area
    special_heritages = models.ManyToManyField(
        "SpecialHeritage",
        blank=True,
        related_name="available_in_areas",
        help_text="Special heritage options available when selecting this area",
    )

    class Meta:
        app_label = "character_creation"
        ordering = ["sort_order", "name"]
        verbose_name = "Starting Area"
        verbose_name_plural = "Starting Areas"

    def __str__(self):
        return self.name

    def is_accessible_by(self, account) -> bool:
        """Check if an account can select this starting area."""
        if not self.is_active:
            return False

        # Staff bypass all restrictions
        if account.is_staff:
            return True

        if self.access_level == self.AccessLevel.STAFF_ONLY:
            return False

        if self.access_level == self.AccessLevel.TRUST_REQUIRED:
            # TODO: Implement trust system check
            # For now, check a simple trust attribute or default to 0
            account_trust = getattr(account, "trust", 0)
            return account_trust >= self.minimum_trust

        return True  # AccessLevel.ALL


class SpecialHeritage(SharedMemoryModel):
    """
    Special heritage types that bypass normal family/species restrictions.

    Examples: Sleeper (awakened from magical slumber, unknown origins),
    Misbegotten (born from Tree of Souls, no parents).

    These allow access to expanded species lists and set family to "Unknown".
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Display name (e.g., 'Sleeper', 'Misbegotten')",
    )
    description = models.TextField(
        help_text="Description explaining this heritage type to players",
    )
    allows_full_species_list = models.BooleanField(
        default=True,
        help_text="If True, players can select any species instead of restricted list",
    )
    family_display = models.CharField(
        max_length=100,
        default="Unknown",
        help_text="What to display for family (e.g., 'Unknown', 'Discoverable in play')",
    )
    starting_room_override = models.ForeignKey(
        ObjectDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="special_heritage_start",
        help_text="Override starting room for this heritage (e.g., Sleeper Wake Room). "
        "If blank, uses area's default room.",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order in selection UI (lower = first)",
    )

    class Meta:
        app_label = "character_creation"
        ordering = ["sort_order", "name"]
        verbose_name = "Special Heritage"
        verbose_name_plural = "Special Heritages"

    def __str__(self):
        return self.name


class CharacterDraft(models.Model):
    """
    In-progress character creation state.

    Stores all staged data as JSON, allowing players to leave and return
    without losing progress. Drafts expire after 2 months of account inactivity.
    """

    class Stage(models.IntegerChoices):
        ORIGIN = 1, "Origin"
        HERITAGE = 2, "Heritage"
        LINEAGE = 3, "Lineage"
        ATTRIBUTES = 4, "Attributes"
        PATH_SKILLS = 5, "Path & Skills"
        TRAITS = 6, "Traits"
        IDENTITY = 7, "Identity"
        REVIEW = 8, "Review"

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        NONBINARY = "nonbinary", "Non-binary"
        OTHER = "other", "Other"

    # Ownership
    account = models.ForeignKey(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="character_drafts",
        help_text="Account creating this character",
    )
    # TODO: Add table FK when Table model exists
    # table = models.ForeignKey(
    #     "tables.Table",
    #     on_delete=models.SET_NULL,
    #     null=True,
    #     blank=True,
    #     help_text="GM table this character is being created for (staff/GM only)",
    # )

    # Stage tracking
    current_stage = models.PositiveSmallIntegerField(
        choices=Stage.choices,
        default=Stage.ORIGIN,
        help_text="Current stage in character creation flow",
    )

    # Stage 1: Origin
    selected_area = models.ForeignKey(
        StartingArea,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Selected starting area",
    )

    # Stage 2: Heritage
    selected_heritage = models.ForeignKey(
        SpecialHeritage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Selected special heritage (null = normal upbringing)",
    )
    species = models.CharField(
        max_length=100,
        blank=True,
        help_text="Selected species",
    )
    gender = models.CharField(
        max_length=20,
        choices=Gender.choices,
        blank=True,
        help_text="Character gender",
    )
    pronoun_subject = models.CharField(
        max_length=20,
        blank=True,
        help_text="Subject pronoun (e.g., 'they')",
    )
    pronoun_object = models.CharField(
        max_length=20,
        blank=True,
        help_text="Object pronoun (e.g., 'them')",
    )
    pronoun_possessive = models.CharField(
        max_length=20,
        blank=True,
        help_text="Possessive pronoun (e.g., 'theirs')",
    )
    age = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Character age in years",
    )

    # Stage 3: Lineage
    family = models.ForeignKey(
        "roster.Family",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="character_drafts",
        help_text="Selected family (null for orphan or special heritage)",
    )
    is_orphan = models.BooleanField(
        default=False,
        help_text="True if character has no family (normal upbringing only)",
    )
    # TODO: bloodline field when Bloodline model exists

    # Stage 4-7: Complex data stored as JSON
    draft_data = models.JSONField(
        default=dict,
        help_text="JSON blob for staged data: stats, skills, traits, identity, etc.",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "character_creation"
        verbose_name = "Character Draft"
        verbose_name_plural = "Character Drafts"

    def __str__(self):
        name = self.draft_data.get("first_name", "Unnamed")
        return f"Draft: {name} ({self.account.username})"

    @property
    def is_expired(self) -> bool:
        """Check if draft has expired due to account inactivity."""
        # Staff drafts don't expire
        if self.account.is_staff:
            return False

        # Expire after 2 months of no updates
        expiry_threshold = timezone.now() - timedelta(days=60)
        return self.updated_at < expiry_threshold

    def get_starting_room(self):
        """
        Resolve the starting room for this character.

        Priority:
        1. Special heritage's starting_room_override
        2. Starting area's default_starting_room
        3. None (valid for Evennia, used during early testing)
        """
        if self.selected_heritage and self.selected_heritage.starting_room_override:
            return self.selected_heritage.starting_room_override

        if self.selected_area and self.selected_area.default_starting_room:
            return self.selected_area.default_starting_room

        return None

    def get_default_pronouns(self) -> dict:
        """Get default pronouns based on gender selection."""
        defaults: dict[str, tuple[str, str, str]] = {
            self.Gender.MALE.value: ("he", "him", "his"),
            self.Gender.FEMALE.value: ("she", "her", "hers"),
            self.Gender.NONBINARY.value: ("they", "them", "theirs"),
            self.Gender.OTHER.value: ("they", "them", "theirs"),
        }
        subject, obj, possessive = defaults.get(self.gender, ("they", "them", "theirs"))
        return {
            "subject": subject,
            "object": obj,
            "possessive": possessive,
        }

    def set_gender_with_defaults(self, gender: str):
        """Set gender and auto-populate pronouns with defaults."""
        self.gender = gender
        pronouns = self.get_default_pronouns()
        self.pronoun_subject = pronouns["subject"]
        self.pronoun_object = pronouns["object"]
        self.pronoun_possessive = pronouns["possessive"]

    def get_stage_completion(self) -> dict[int, bool]:
        """
        Check completion status of each stage.

        Returns dict mapping stage number to completion boolean.
        """
        return {
            self.Stage.ORIGIN: self.selected_area is not None,
            self.Stage.HERITAGE: bool(self.species and self.gender and self.age),
            self.Stage.LINEAGE: self._is_lineage_complete(),
            self.Stage.ATTRIBUTES: self._is_attributes_complete(),
            self.Stage.PATH_SKILLS: self._is_path_skills_complete(),
            self.Stage.TRAITS: self._is_traits_complete(),
            self.Stage.IDENTITY: self._is_identity_complete(),
            self.Stage.REVIEW: False,  # Review is never "complete" - it's the final step
        }

    def _is_lineage_complete(self) -> bool:
        """Check if lineage stage is complete."""
        # Special heritage = always complete (family is "Unknown")
        if self.selected_heritage:
            return True
        # Normal upbringing needs family or explicit orphan
        return self.family is not None or self.is_orphan

    def _is_attributes_complete(self) -> bool:
        """Check if attributes stage is complete."""
        # TODO: Implement when stats system exists
        return bool(self.draft_data.get("attributes_complete", False))

    def _is_path_skills_complete(self) -> bool:
        """Check if path & skills stage is complete."""
        # TODO: Implement when path/skills system exists
        return bool(self.draft_data.get("path_skills_complete", False))

    def _is_traits_complete(self) -> bool:
        """Check if traits stage is complete."""
        # TODO: Implement when traits system exists
        return bool(self.draft_data.get("traits_complete", False))

    def _is_identity_complete(self) -> bool:
        """Check if identity stage is complete."""
        data = self.draft_data
        return bool(data.get("first_name") and data.get("description"))

    def can_submit(self) -> bool:
        """Check if all required stages are complete for submission."""
        completion = self.get_stage_completion()
        # All stages except REVIEW must be complete
        required_stages = [s for s in self.Stage if s != self.Stage.REVIEW]
        return all(completion.get(stage, False) for stage in required_stages)
