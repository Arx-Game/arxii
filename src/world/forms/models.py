from django.db import models
from django.utils import timezone
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from world.species.models import Species, SpeciesOrigin


class TraitType(models.TextChoices):
    COLOR = "color", "Color"
    STYLE = "style", "Style"


class HeightBand(SharedMemoryModel):
    """Defines height ranges that map to descriptive bands."""

    name = models.CharField(max_length=50, unique=True, help_text="Internal key")
    display_name = models.CharField(max_length=100, help_text="Display name")
    min_inches = models.PositiveSmallIntegerField(help_text="Minimum height in inches (inclusive)")
    max_inches = models.PositiveSmallIntegerField(help_text="Maximum height in inches (inclusive)")
    weight_min = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minimum weight in pounds (for extreme bands)",
    )
    weight_max = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum weight in pounds (for extreme bands)",
    )
    is_cg_selectable = models.BooleanField(
        default=False,
        help_text="Whether players can select heights in this band during CG",
    )
    hide_build = models.BooleanField(
        default=False,
        help_text="Hide build display at this scale (e.g., dragon-size)",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "min_inches"]

    def __str__(self):
        return self.display_name

    @property
    def midpoint(self) -> int:
        """Return the midpoint of this band's range."""
        return (self.min_inches + self.max_inches) // 2


class Build(SharedMemoryModel):
    """Defines body type options with weight calculation factors."""

    name = models.CharField(max_length=50, unique=True, help_text="Internal key")
    display_name = models.CharField(max_length=100, help_text="Display name")
    weight_factor = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        help_text="Multiplier for weight calculation (height × factor = weight)",
    )
    is_cg_selectable = models.BooleanField(
        default=True,
        help_text="Whether available in character creation",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "display_name"]

    def __str__(self):
        return self.display_name


class FormTrait(SharedMemoryModel):
    """Definition of a physical characteristic type (e.g., hair_color, ear_type)."""

    name = models.CharField(max_length=50, unique=True, help_text="Internal key")
    display_name = models.CharField(max_length=100, help_text="Display name for UI")
    trait_type = models.CharField(max_length=20, choices=TraitType.choices, default=TraitType.STYLE)
    sort_order = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return self.display_name


class FormTraitOption(SharedMemoryModel):
    """A valid value for a trait (e.g., 'black' for hair_color)."""

    trait = models.ForeignKey(FormTrait, on_delete=models.CASCADE, related_name="options")
    name = models.CharField(max_length=50, help_text="Internal key")
    display_name = models.CharField(max_length=100, help_text="Display name for UI")
    sort_order = models.PositiveSmallIntegerField(default=0)
    height_modifier_inches = models.SmallIntegerField(
        null=True,
        blank=True,
        help_text="Inches added to apparent height when visible (e.g., horns)",
    )

    class Meta:
        unique_together = [["trait", "name"]]

    def __str__(self):
        return f"{self.trait.display_name}: {self.display_name}"


class SpeciesFormTrait(SharedMemoryModel):
    """Links a species to which traits it has available in CG."""

    species = models.ForeignKey(Species, on_delete=models.CASCADE, related_name="form_traits")
    trait = models.ForeignKey(FormTrait, on_delete=models.CASCADE, related_name="species_links")
    is_available_in_cg = models.BooleanField(
        default=True, help_text="Show this trait in character creation"
    )

    class Meta:
        unique_together = [["species", "trait"]]
        verbose_name = "Species Form Trait"
        verbose_name_plural = "Species Form Traits"

    def __str__(self):
        return f"{self.species.name} - {self.trait.display_name}"


class SpeciesOriginTraitOption(SharedMemoryModel):
    """Override available options for a trait at the origin level."""

    species_origin = models.ForeignKey(
        SpeciesOrigin, on_delete=models.CASCADE, related_name="trait_option_overrides"
    )
    option = models.ForeignKey(
        FormTraitOption, on_delete=models.CASCADE, related_name="origin_overrides"
    )
    is_available = models.BooleanField(
        default=True, help_text="True=add this option, False=remove it"
    )

    class Meta:
        unique_together = [["species_origin", "option"]]
        verbose_name = "Species Origin Trait Option"
        verbose_name_plural = "Species Origin Trait Options"

    @property
    def trait(self) -> FormTrait:
        """Get the trait this option belongs to."""
        return self.option.trait

    def __str__(self):
        action = "+" if self.is_available else "-"
        return f"{self.species_origin}: {action}{self.option.display_name}"


class FormType(models.TextChoices):
    TRUE = "true", "True Form"
    ALTERNATE = "alternate", "Alternate Form"
    DISGUISE = "disguise", "Disguise"


class SourceType(models.TextChoices):
    EQUIPPED_ITEM = "equipped_item", "Equipped Item"
    APPLIED_ITEM = "applied_item", "Applied Item"
    SPELL = "spell", "Spell"
    SYSTEM = "system", "System"


class DurationType(models.TextChoices):
    UNTIL_REMOVED = "until_removed", "Until Removed"
    REAL_TIME = "real_time", "Real Time"
    GAME_TIME = "game_time", "Game Time"
    SCENE = "scene", "Scene-Based"


class CharacterForm(models.Model):
    """A saved set of form trait values for a character."""

    character = models.ForeignKey(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="forms",
        limit_choices_to={"db_typeclass_path__contains": "Character"},
    )
    name = models.CharField(max_length=100, blank=True, help_text="Optional form name")
    form_type = models.CharField(max_length=20, choices=FormType.choices, default=FormType.TRUE)
    is_player_created = models.BooleanField(
        default=False, help_text="True for player-created disguises"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Character Form"
        verbose_name_plural = "Character Forms"

    def __str__(self):
        if self.name:
            return f"{self.character.db_key}: {self.name}"
        return f"{self.character.db_key}: {self.get_form_type_display()}"


class CharacterFormValue(models.Model):
    """A single trait value within a character's form."""

    form = models.ForeignKey(CharacterForm, on_delete=models.CASCADE, related_name="values")
    trait = models.ForeignKey(FormTrait, on_delete=models.CASCADE, related_name="character_values")
    option = models.ForeignKey(
        FormTraitOption, on_delete=models.CASCADE, related_name="character_values"
    )

    class Meta:
        unique_together = [["form", "trait"]]
        verbose_name = "Character Form Value"
        verbose_name_plural = "Character Form Values"

    def __str__(self):
        return f"{self.form}: {self.trait.display_name}={self.option.display_name}"


class CharacterFormState(models.Model):
    """Tracks which form a character currently has active."""

    character = models.OneToOneField(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="form_state",
        limit_choices_to={"db_typeclass_path__contains": "Character"},
    )
    active_form = models.ForeignKey(
        CharacterForm,
        on_delete=models.SET_NULL,
        null=True,
        related_name="active_for",
    )

    class Meta:
        verbose_name = "Character Form State"
        verbose_name_plural = "Character Form States"

    def __str__(self):
        if self.active_form:
            return f"{self.character.db_key}: {self.active_form}"
        return f"{self.character.db_key}: No active form"


class TemporaryFormChangeManager(models.Manager):
    """Manager with convenience methods for temporary changes."""

    def active(self):
        """Return non-expired temporary changes."""
        now = timezone.now()
        return self.exclude(duration_type=DurationType.REAL_TIME, expires_at__lt=now)


class TemporaryFormChange(models.Model):
    """A temporary override applied on top of the active form."""

    character = models.ForeignKey(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="temporary_form_changes",
        limit_choices_to={"db_typeclass_path__contains": "Character"},
    )
    trait = models.ForeignKey(FormTrait, on_delete=models.CASCADE, related_name="temporary_changes")
    option = models.ForeignKey(
        FormTraitOption, on_delete=models.CASCADE, related_name="temporary_changes"
    )
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    source_id = models.PositiveIntegerField(
        null=True, blank=True, help_text="ID of the source object"
    )
    duration_type = models.CharField(max_length=20, choices=DurationType.choices)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="For real-time duration")
    expires_after_scenes = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="For scene-based duration"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TemporaryFormChangeManager()

    class Meta:
        verbose_name = "Temporary Form Change"
        verbose_name_plural = "Temporary Form Changes"

    def __str__(self):
        return (
            f"{self.character.db_key}: {self.trait.display_name}="
            f"{self.option.display_name} ({self.get_duration_type_display()})"
        )

    def is_expired(self) -> bool:
        """Check if this temporary change has expired."""
        if self.duration_type == DurationType.UNTIL_REMOVED:
            return False
        if self.duration_type == DurationType.REAL_TIME and self.expires_at:
            return timezone.now() > self.expires_at
        # Game time and scene-based require external tracking
        return False
