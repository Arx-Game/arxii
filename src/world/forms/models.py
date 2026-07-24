from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.species.models import Species

SCENES_PERSONA_FK = "scenes.Persona"


class TraitType(models.TextChoices):
    COLOR = "color", "Color"
    STYLE = "style", "Style"


class HeightBand(NaturalKeyMixin, SharedMemoryModel):
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

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["sort_order", "min_inches"]

    def __str__(self):
        return self.display_name

    @property
    def midpoint(self) -> int:
        """Return the midpoint of this band's range."""
        return (self.min_inches + self.max_inches) // 2


class Build(NaturalKeyMixin, SharedMemoryModel):
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

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["sort_order", "display_name"]

    def __str__(self):
        return self.display_name


class FormTrait(NaturalKeyMixin, SharedMemoryModel):
    """Definition of a physical characteristic type (e.g., hair_color, ear_type)."""

    name = models.CharField(max_length=50, unique=True, help_text="Internal key")
    display_name = models.CharField(max_length=100, help_text="Display name for UI")
    trait_type = models.CharField(max_length=20, choices=TraitType.choices, default=TraitType.STYLE)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_cosmetic = models.BooleanField(
        default=False,
        help_text=(
            "Player may self-edit this trait cosmetically (hair dye, makeup, restyle) "
            "without magic. Fixed traits (height, species markers) stay False."
        ),
    )
    composite_option = models.ForeignKey(
        "forms.FormTraitOption",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="composite_for_traits",
        help_text=(
            "The umbrella value blends resolve to (#2632 — hair_color: multihued, "
            "eye_color: mismatched). Null = this trait does not support blends. "
            "The blend's actual colors live in FormValueComponent rows, so the "
            "normalized layer can still say 'red-green' under descriptor "
            "concealment without the distinctive prose."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self):
        return self.display_name

    @cached_property
    def cached_options(self) -> list["FormTraitOption"]:
        """
        Get options for this trait.

        This cached_property serves as the target for Prefetch(..., to_attr=).
        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.

        To invalidate: del instance.cached_options
        """
        return list(self.options.all())


class FormTraitOption(NaturalKeyMixin, SharedMemoryModel):
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
    requires_teaching = models.BooleanField(
        default=False,
        help_text=(
            "Exotic option gated on knowing it (#2632 — 'learned/taught, another "
            "crafting recipe almost'). A choose-at-use cosmetic (Styling Kit) "
            "refuses it unless the ACTING character holds a CharacterKnownStyle; "
            "having it done on you (NPC stylist, a knowing PC stylist) teaches it."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["trait", "name"]
        dependencies = ["forms.FormTrait"]

    class Meta:
        unique_together = [["trait", "name"]]

    def __str__(self):
        return f"{self.trait.display_name}: {self.display_name}"


class SpeciesFormTrait(NaturalKeyMixin, SharedMemoryModel):
    """Links a species to which traits and options it has available in CG."""

    species = models.ForeignKey(Species, on_delete=models.CASCADE, related_name="form_traits")
    trait = models.ForeignKey(FormTrait, on_delete=models.CASCADE, related_name="species_links")
    is_available_in_cg = models.BooleanField(
        default=True, help_text="Show this trait in character creation"
    )
    allowed_options = models.ManyToManyField(
        FormTraitOption,
        blank=True,
        related_name="species_restrictions",
        help_text="If empty, all options are available. If set, only these options are shown.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["species", "trait"]
        dependencies = ["species.Species", "forms.FormTrait"]

    class Meta:
        unique_together = [["species", "trait"]]
        verbose_name = "Species Form Trait"
        verbose_name_plural = "Species Form Traits"

    def __str__(self):
        return f"{self.species.name} - {self.trait.display_name}"

    @cached_property
    def cached_allowed_options(self) -> list["FormTraitOption"]:
        """
        Get allowed options for this species-trait combination.

        This cached_property serves as the target for Prefetch(..., to_attr=).
        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.

        To invalidate: del instance.cached_allowed_options
        """
        return list(self.allowed_options.all())

    def get_available_options(self):
        """
        Get options available for this species-trait combination.

        Returns allowed_options if set, otherwise all options for the trait.
        Uses cached_allowed_options when available (via Prefetch to_attr or
        cached_property fallback).
        """
        allowed = self.cached_allowed_options
        if allowed:
            return sorted(allowed, key=lambda o: (o.sort_order, o.display_name))
        return self.trait.cached_options or list(
            self.trait.options.all().order_by("sort_order", "display_name")
        )


class FormType(models.TextChoices):
    TRUE = "true", "True Form"
    ALTERNATE = "alternate", "Alternate Form"
    DISGUISE = "disguise", "Disguise"


class DisguiseKind(models.TextChoices):
    """How a fake overlay is defeated (#1110). The pierce *contest* itself is the senior dev's
    domain (perception-vs-disguise / dispel); this just records which contest applies."""

    MUNDANE = "mundane", "Mundane Disguise"  # defeated by perception / inspection
    MAGICAL = "magical", "Magical Illusion"  # defeated by dispel / see-magic


class ConcealmentLevel(models.TextChoices):
    """What a disguise overlay conceals from an unpierced viewer (#1272).

    The control lives on the disguise form, not on the traits themselves — a given
    disguise declares what it hides. The pierce *contest* (perception/dispel) is the
    senior dev's domain; this just records the level its outcome reads through.
    """

    NONE = "none", "No Concealment"  # full trait + descriptor visible (default)
    DESCRIPTOR = "descriptor", "Descriptor Only"  # normalized value visible, descriptor hidden
    FULL = "full", "Full Concealment"  # traits hidden entirely


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


class CharacterForm(SharedMemoryModel):
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
    concealment_level = models.CharField(
        max_length=20,
        choices=ConcealmentLevel.choices,
        default=ConcealmentLevel.NONE,
        help_text=(
            "What this disguise conceals from an unpierced viewer (#1272): "
            "NONE = full trait + descriptor, DESCRIPTOR = value only, FULL = nothing."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Character Form"
        verbose_name_plural = "Character Forms"

    def __str__(self):
        if self.name:
            return f"{self.character.db_key}: {self.name}"
        return f"{self.character.db_key}: {self.get_form_type_display()}"

    @cached_property
    def cached_values(self) -> list["CharacterFormValue"]:
        """
        Get form values with related trait and option loaded.

        This cached_property serves as the target for Prefetch(..., to_attr=).
        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.

        To invalidate: del instance.cached_values
        """
        return list(self.values.select_related("trait", "option"))


class CharacterFormValue(SharedMemoryModel):
    """A single trait value within a character's form."""

    form = models.ForeignKey(CharacterForm, on_delete=models.CASCADE, related_name="values")
    trait = models.ForeignKey(FormTrait, on_delete=models.CASCADE, related_name="character_values")
    option = models.ForeignKey(
        FormTraitOption, on_delete=models.CASCADE, related_name="character_values"
    )
    natural_option = models.ForeignKey(
        FormTraitOption,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="natural_for_values",
        help_text=(
            "The original/natural value — the 'reset to natural' target. Set at "
            "creation; cosmetic edits change ``option`` but never this."
        ),
    )

    class Meta:
        unique_together = [["form", "trait"]]
        verbose_name = "Character Form Value"
        verbose_name_plural = "Character Form Values"

    def __str__(self):
        return f"{self.form}: {self.trait.display_name}={self.option.display_name}"


class CharacterFormState(SharedMemoryModel):
    """The character's two-slot active appearance state (#1110).

    - ``active_form`` is the **current real form** — what the body actually is right now (the true
      form unless shapeshifted). Shapeshift swaps this slot; it is always REAL.
    - ``active_fake_overlay`` is an optional **fake overlay** (a ``DISGUISE`` form) painted *over*
      the real form. The real form is preserved beneath and seen when the overlay is pierced.
      Single-slot for now (ordered-stack stacking is a deferred decision).

    Owner/staff ground-truth reads ignore the overlay and read ``active_form``; everyone else's
    composed view swaps in the overlay until they pierce it. The pierce *contest* (perception vs
    disguise / dispel) is the senior dev's domain — this only holds the slots + ``overlay_kind``.
    """

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
        help_text="The current REAL form (what the body actually is now).",
    )
    active_fake_overlay = models.ForeignKey(
        CharacterForm,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="overlay_for",
        help_text="Optional FAKE overlay (a DISGUISE form) presented over the real form (#1110).",
    )
    overlay_kind = models.CharField(
        max_length=20,
        choices=DisguiseKind.choices,
        blank=True,
        default="",
        help_text="How the active overlay is pierced (mundane vs magical). Blank ⇒ no overlay.",
    )
    applied_kit_instance = models.ForeignKey(
        "items.ItemInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applied_disguise_overlays",
        help_text=(
            "The disguise-kit ItemInstance whose use applied the active overlay (#2249). "
            "Null when the overlay was applied narratively (not from a kit). "
            "Cleared when the overlay is removed."
        ),
    )

    class Meta:
        verbose_name = "Character Form State"
        verbose_name_plural = "Character Form States"

    @property
    def current_real_form(self) -> "CharacterForm | None":
        """The current real form — the canonical name for the ``active_form`` slot (#1110)."""
        return self.active_form

    def __str__(self):
        if self.active_form:
            return f"{self.character.db_key}: {self.active_form}"
        return f"{self.character.db_key}: No active form"


class FormCombatProfile(SharedMemoryModel):
    """A battle form's stat-suite — a package of stat modifiers applied while the form
    is active. Owns its ModifierSource rows; created on assumption, deleted on revert.
    """

    form = models.ForeignKey(
        CharacterForm,
        on_delete=models.CASCADE,
        related_name="combat_profiles",
        help_text="The ALTERNATE form this stat-suite belongs to.",
    )
    display_name = models.CharField(max_length=100, blank=True)
    depth = models.PositiveSmallIntegerField(
        default=0,
        help_text="Profile tier within the form; higher bands select deeper profiles.",
    )

    class Meta:
        ordering = ["form", "depth", "display_name"]

    def __str__(self) -> str:
        return self.display_name or f"{self.form} profile"


class FormCombatProfileEffect(SharedMemoryModel):
    """One stat modifier in a form's combat profile."""

    profile = models.ForeignKey(FormCombatProfile, on_delete=models.CASCADE, related_name="effects")
    target = models.ForeignKey(
        "mechanics.ModifierTarget", on_delete=models.CASCADE, related_name="form_effects"
    )
    value = models.IntegerField(help_text="Modifier value (can be negative).")

    class Meta:
        ordering = ["profile", "target"]

    def __str__(self) -> str:
        return f"{self.profile}: {self.target} {self.value:+d}"


class AlternateSelf(SharedMemoryModel):
    """A character's access to an alternate self — a bundle of optional facets (form,
    stats, abilities, persona) swapped together on assumption. Each facet pointer is
    optional and may reference a shared catalog template or a unique one. ``tuning_value``
    parameterizes a shared template per-character (e.g. lycanthropy-thread strength).
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="alternate_selves",
    )
    form = models.ForeignKey(
        CharacterForm,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="alternate_self_grants",
    )
    persona = models.ForeignKey(
        SCENES_PERSONA_FK,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alternate_self_grants",
    )
    combat_profile = models.ForeignKey(
        FormCombatProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="grants",
    )
    techniques = models.ManyToManyField(
        "magic.Technique", blank=True, related_name="alternate_self_grants"
    )
    tuning_value = models.IntegerField(null=True, blank=True)
    display_name = models.CharField(max_length=100, blank=True)
    thumbnail = models.ForeignKey(
        "evennia_extensions.Media",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alternate_self_thumbnails",
        help_text=(
            "Thumbnail shown when this alternate self is active (overrides persona default)"
        ),
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="alternate_self_grants",
        help_text=(
            "When set, assuming this alternate self shifts the character's "
            "technique variant resolution to this resonance (#1619). The GIFT "
            "thread's level still determines which variant tier unlocks; only "
            "the resonance axis changes. Null = no resonance shift."
        ),
    )

    class Meta:
        ordering = ["character", "display_name"]

    def __str__(self) -> str:
        return self.display_name or f"{self.character} alt-self"


class ActiveAlternateSelf(SharedMemoryModel):
    """The currently-assumed alternate self + per-facet return anchors. One per character.
    Holds return_form/return_persona (the form/persona to revert to). ``in_control`` is a
    DERIVED property (added in a later task) — NOT stored here.
    """

    character = models.OneToOneField(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="active_alternate_self",
    )
    alternate_self = models.ForeignKey(
        AlternateSelf,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="active_for",
    )
    return_form = models.ForeignKey(
        CharacterForm,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="return_for_active",
    )
    return_persona = models.ForeignKey(
        SCENES_PERSONA_FK,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="return_for_active",
    )

    class Meta:
        ordering = ["character"]

    def __str__(self) -> str:
        return f"{self.character}: {self.alternate_self or 'no active alt-self'}"


class TemporaryFormChangeManager(models.Manager):
    """Manager with convenience methods for temporary changes."""

    def active(self):
        """Return non-expired temporary changes."""
        now = timezone.now()
        return self.exclude(duration_type=DurationType.REAL_TIME, expires_at__lt=now)


class TemporaryFormChange(SharedMemoryModel):
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


class PersonaTraitDescriptor(SharedMemoryModel):
    """A persona's free-text flavor for one appearance trait (red hair -> 'Crimson').

    Scoped per ``(persona, trait)`` so one shared physical form can read differently
    under different personas. The descriptor is identity-bearing and therefore never
    auto-copied across a character's personas (the descriptor privacy invariant —
    enforced once multi-persona creation lands, slice 2). Absence of a row means "no
    descriptor": rendering falls back to the normalized option's display value.
    """

    persona = models.ForeignKey(
        SCENES_PERSONA_FK,
        on_delete=models.CASCADE,
        related_name="trait_descriptors",
        help_text="The presented face this descriptor belongs to.",
    )
    trait = models.ForeignKey(
        FormTrait,
        on_delete=models.CASCADE,
        related_name="persona_descriptors",
        help_text="The appearance trait this describes.",
    )
    text = models.CharField(
        max_length=120,
        help_text="Free-text flavor for the trait (e.g. 'Robin's-egg', 'Crimson').",
    )

    class Meta:
        unique_together = [["persona", "trait"]]
        ordering = ["persona", "trait"]
        verbose_name = "Persona Trait Descriptor"
        verbose_name_plural = "Persona Trait Descriptors"

    def __str__(self):
        return f"{self.persona}: {self.trait.display_name}='{self.text}'"


class AppearanceChangeLog(SharedMemoryModel):
    """Append-only record of an appearance edit, for continuity across roster handoffs.

    Captures what changed, who changed it, and an optional note, so a player who
    inherits a roster character can see that the blue hair was dyed — and what it was
    before.
    """

    form = models.ForeignKey(
        CharacterForm,
        on_delete=models.CASCADE,
        related_name="appearance_changes",
        help_text="The real form whose trait was edited.",
    )
    persona = models.ForeignKey(
        SCENES_PERSONA_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appearance_changes",
        help_text="The persona presenting when the edit was made (descriptor owner).",
    )
    trait = models.ForeignKey(
        FormTrait, on_delete=models.CASCADE, related_name="appearance_changes"
    )
    from_option = models.ForeignKey(
        FormTraitOption, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    to_option = models.ForeignKey(
        FormTraitOption, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    from_text = models.CharField(max_length=120, blank=True, help_text="Prior descriptor.")
    to_text = models.CharField(max_length=120, blank=True, help_text="New descriptor.")
    actor_persona = models.ForeignKey(
        SCENES_PERSONA_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appearance_changes_made",
        help_text="Who made the change (own persona for self-edits; null for system/staff).",
    )
    note = models.CharField(max_length=255, blank=True, help_text="Optional in-fiction note.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Appearance Change Log"
        verbose_name_plural = "Appearance Change Logs"

    def __str__(self):
        return f"{self.form}: {self.trait.display_name} change"


class FormValueComponent(SharedMemoryModel):
    """One component color/value of a blended trait value (#2632).

    When a ``CharacterFormValue`` sits on its trait's ``composite_option``
    (multihued hair, mismatched eyes), these rows list the ACTUAL components
    in order — so the normalized layer can render "red-green" instead of the
    umbrella word alone. This matters under disguise: descriptor concealment
    hides the distinctive prose, but "a masked figure with red-green hair" is
    what a witness genuinely sees, and hiding the components would leak less
    than reality warrants.
    """

    value = models.ForeignKey(
        CharacterFormValue,
        on_delete=models.CASCADE,
        related_name="components",
    )
    option = models.ForeignKey(
        FormTraitOption,
        on_delete=models.PROTECT,
        related_name="component_of_values",
        help_text="One actual component of the blend (e.g. 'red').",
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Blend order — first is the base/dominant component.",
    )

    class Meta:
        unique_together = [["value", "option"]]
        ordering = ["sort_order", "pk"]
        verbose_name = "Form Value Component"
        verbose_name_plural = "Form Value Components"

    def __str__(self):
        return f"{self.value_id}: {self.option.display_name} (#{self.sort_order})"


class CharacterKnownStyle(SharedMemoryModel):
    """A character knows how to produce an exotic (requires_teaching) option (#2632).

    Learned by having it done: an NPC stylist's exotic service, or a knowing PC
    stylist applying it to you, grants the row. A choose-at-use cosmetic
    (Styling Kit) requires the ACTING character to hold one for the option.
    """

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="known_styles",
    )
    option = models.ForeignKey(
        FormTraitOption,
        on_delete=models.CASCADE,
        related_name="knowers",
    )
    learned_at = models.DateTimeField(auto_now_add=True)
    taught_by_label = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Display name of who taught it (stylist NPC, a PC stylist).",
    )

    class Meta:
        unique_together = [["character_sheet", "option"]]
        verbose_name = "Character Known Style"
        verbose_name_plural = "Character Known Styles"

    def __str__(self):
        return f"sheet {self.character_sheet_id} knows {self.option.display_name}"
