"""
Character sheet models for storing character demographic and descriptive data.

This replaces Arx I's character data stored in Evennia attributes with proper
Django models for better data integrity, querying, and performance.

Based on Arx I's evennia_extensions/character_extensions/models.py patterns
and the evennia_extensions/object_extensions/models.py display name system.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from world.character_sheets.types import Gender, MaritalStatus


class Race(SharedMemoryModel):
    """
    Base races available in character creation.

    Uses SharedMemoryModel for performance since these are lookup tables
    that are accessed frequently but changed rarely.
    """

    name = models.CharField(
        max_length=100, unique=True, help_text="Race name (e.g., Human, Elven)"
    )
    description = models.TextField(help_text="Description of this race")
    allowed_in_chargen = models.BooleanField(
        default=True,
        help_text="Whether this race is available during character creation",
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Race"
        verbose_name_plural = "Races"
        ordering = ["name"]


class Subrace(SharedMemoryModel):
    """
    Subspecialization of races (e.g., Nox'alfar, Sylv'alfar for Elven).

    Uses SharedMemoryModel for performance since these are lookup tables
    that are accessed frequently but changed rarely.
    """

    race = models.ForeignKey(
        Race,
        on_delete=models.CASCADE,
        related_name="subraces",
        help_text="The parent race this subrace belongs to",
    )
    name = models.CharField(max_length=100, help_text="Subrace name (e.g., Nox'alfar)")
    description = models.TextField(help_text="Description of this subrace")
    allowed_in_chargen = models.BooleanField(
        default=True,
        help_text="Whether this subrace is available during character creation",
    )

    # Many-to-many relationships for characteristics
    additional_characteristics = models.ManyToManyField(
        "Characteristic",
        blank=True,
        related_name="required_by_subraces",
        help_text="Characteristics that this subrace adds beyond the parent race",
    )
    excluded_characteristics = models.ManyToManyField(
        "Characteristic",
        blank=True,
        related_name="excluded_by_subraces",
        help_text="Characteristics that this subrace cannot have",
    )

    def __str__(self):
        return f"{self.race.name} - {self.name}"

    class Meta:
        verbose_name = "Subrace"
        verbose_name_plural = "Subraces"
        unique_together = [["race", "name"]]
        ordering = ["race__name", "name"]


class CharacterSheet(models.Model):
    """
    Primary character demographic and identity data storage.

    Replaces Arx I's CharacterSheet model and item_data attribute system
    with proper Django model fields for better data integrity and querying.
    """

    character = models.OneToOneField(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="sheet_data",
        primary_key=True,
        help_text="The character this sheet belongs to",
    )

    # Basic Identity & Demographics
    age = models.PositiveSmallIntegerField(
        default=18,
        validators=[MinValueValidator(16), MaxValueValidator(200)],
        help_text="Character's apparent age",
    )
    real_age = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10000)],
        help_text="Character's true age (staff/hidden field)",
    )
    gender = models.CharField(
        max_length=20,
        choices=Gender.choices,
        default=Gender.MALE,
        help_text="Character's gender identity",
    )

    # Race and Subrace
    race = models.ForeignKey(
        Race,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="character_sheets",
        help_text="Character's base race",
    )
    subrace = models.ForeignKey(
        Subrace,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="character_sheets",
        help_text="Character's subrace (optional)",
    )

    # Social & Identity
    concept = models.CharField(
        max_length=255, blank=True, help_text="Public character concept/archetype"
    )
    real_concept = models.CharField(
        max_length=255,
        blank=True,
        help_text="Hidden/secret character concept (staff field)",
    )
    marital_status = models.CharField(
        max_length=20,
        choices=MaritalStatus.choices,
        default=MaritalStatus.SINGLE,
        help_text="Character's marital status",
    )
    family = models.CharField(
        max_length=255,
        blank=True,
        help_text="Family name - will be converted to FK later",
    )
    vocation = models.CharField(
        max_length=255, blank=True, help_text="Character profession - will be FK later"
    )
    social_rank = models.PositiveSmallIntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="Social standing/rank (1=highest, 20=lowest)",
    )

    # Temporal & Cultural
    birthday = models.CharField(
        max_length=255,
        blank=True,
        help_text="Character birthday - consider DateField later",
    )

    # Descriptive Text Fields
    quote = models.TextField(blank=True, help_text="Character quote/motto")
    personality = models.TextField(
        blank=True, help_text="Character personality description"
    )
    background = models.TextField(blank=True, help_text="Character background story")
    obituary = models.TextField(
        blank=True, help_text="Death notice if character is deceased"
    )
    additional_desc = models.TextField(
        blank=True, help_text="Additional character description"
    )

    # Timestamps
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Sheet for {self.character.key}"

    class Meta:
        verbose_name = "Character Sheet"
        verbose_name_plural = "Character Sheets"


# CharacterDescription model removed - functionality moved to:
# - evennia_extensions.ObjectDisplayData for basic display info
#   (colored_name, longname, descriptions)
# - world.character_sheets.Guise for false names and contextual appearances


class Guise(models.Model):
    """
    Contextual character representation for scenes and disguises.

    Based on the Guise system described in scenes-technical.md.
    Allows characters to appear differently in scenes through disguises,
    transformations, or when playing NPCs.
    """

    character = models.ForeignKey(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="guises",
        help_text="The character this guise belongs to",
    )

    name = models.CharField(max_length=255, help_text="Display name for this guise")
    colored_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name with color formatting codes for this guise",
    )
    description = models.TextField(
        blank=True, help_text="Physical description text for this guise"
    )
    thumbnail = models.ForeignKey(
        "evennia_extensions.PlayerMedia",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="guise_thumbnails",
        help_text="Visual representation for this guise",
    )
    is_default = models.BooleanField(
        default=False, help_text="Whether this is the character's standard guise"
    )

    # Timestamps
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Ensure only one default guise per character
        if self.is_default:
            Guise.objects.filter(character=self.character, is_default=True).exclude(
                pk=self.pk
            ).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        default_str = " (default)" if self.is_default else ""
        return f"{self.name} for {self.character.key}{default_str}"

    class Meta:
        verbose_name = "Character Guise"
        verbose_name_plural = "Character Guises"
        unique_together = [["character", "name"]]


class Characteristic(SharedMemoryModel):
    """
    Defines types of physical characteristics characters can have.

    Uses SharedMemoryModel for performance since these are lookup tables
    that are accessed frequently but changed rarely.

    Examples: eye_color, hair_color, height, skin_tone, etc.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Internal name for this characteristic type",
    )
    display_name = models.CharField(
        max_length=100, help_text="Human-readable name for this characteristic"
    )
    description = models.TextField(
        blank=True, help_text="Description of what this characteristic represents"
    )
    is_active = models.BooleanField(
        default=True, help_text="Whether this characteristic is available for use"
    )

    # For future expansion - different races might have different characteristics
    required_for_races = models.JSONField(
        default=list,
        blank=True,
        help_text="List of race names this characteristic is required for",
    )

    def __str__(self):
        return self.display_name

    class Meta:
        verbose_name = "Characteristic Type"
        verbose_name_plural = "Characteristic Types"
        ordering = ["display_name"]


class CharacteristicValue(SharedMemoryModel):
    """
    Specific values available for each characteristic type.

    Uses SharedMemoryModel for performance. Links to Characteristic to define
    what values are valid for each type.

    Examples: For eye_color - "blue", "green", "brown", etc.
    """

    characteristic = models.ForeignKey(
        Characteristic,
        on_delete=models.CASCADE,
        related_name="values",
        help_text="The characteristic type this value belongs to",
    )
    value = models.CharField(
        max_length=100, help_text="The specific value (e.g., 'blue', 'tall', etc.)"
    )
    display_value = models.CharField(
        max_length=100,
        blank=True,
        help_text="Display version of the value (defaults to value)",
    )
    description = models.TextField(
        blank=True, help_text="Optional description of this value"
    )
    is_active = models.BooleanField(
        default=True, help_text="Whether this value is available for selection"
    )

    # Race restrictions - normalized relationships instead of JSONField
    allowed_for_races = models.ManyToManyField(
        Race,
        blank=True,
        related_name="allowed_characteristic_values",
        help_text="Races this value is allowed for (empty = all races)",
    )

    def save(self, *args, **kwargs):
        if not self.display_value:
            self.display_value = self.value
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.characteristic.display_name}: {self.display_value}"

    class Meta:
        verbose_name = "Characteristic Value"
        verbose_name_plural = "Characteristic Values"
        unique_together = [["characteristic", "value"]]
        ordering = ["characteristic__display_name", "display_value"]


class CharacterSheetValue(models.Model):
    """
    Links characters to their specific characteristic values.

    This is the many-to-many through model that stores which characteristic
    values each character has selected.
    """

    character_sheet = models.ForeignKey(
        CharacterSheet,
        on_delete=models.CASCADE,
        related_name="characteristic_values",
        help_text="The character sheet this value belongs to",
    )
    characteristic_value = models.ForeignKey(
        CharacteristicValue,
        on_delete=models.CASCADE,
        related_name="character_sheets",
        help_text="The characteristic value assigned to this character",
    )

    # Timestamps
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def clean(self):
        """Validate that character doesn't already have a value for this characteristic."""
        super().clean()

        if self.character_sheet and self.characteristic_value:
            # Check if character already has a value for this characteristic
            existing = CharacterSheetValue.objects.filter(
                character_sheet=self.character_sheet,
                characteristic_value__characteristic=self.characteristic_value.characteristic,
            ).exclude(pk=self.pk)

            if existing.exists():
                from django.core.exceptions import ValidationError

                raise ValidationError(
                    f"Character already has a value for "
                    f"{self.characteristic_value.characteristic.display_name}"
                )

    def save(self, *args, **kwargs):
        """Override save to run validation."""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.character_sheet.character.key}: " f"{self.characteristic_value}"

    class Meta:
        verbose_name = "Character Characteristic Value"
        verbose_name_plural = "Character Characteristic Values"
        unique_together = [["character_sheet", "characteristic_value"]]
