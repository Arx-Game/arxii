"""Check system models."""

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.areas.positioning.constants import PositionKind
from world.checks.constants import EffectTarget, EffectType, PositionDestination

# Import outcome models so migrations and admin discover them.
from world.checks.outcome_models import ConsequenceOutcome, ConsequenceOutcomeModifier  # noqa: F401


class OutcomeTierAward(SharedMemoryModel):
    """Shared base: one authored scalar per graded CheckOutcome tier.

    Generalizes the pattern `world.societies.models.GangTurfReputationAward`
    already used correctly — a staff-tunable DB row per canonical outcome tier,
    instead of a bespoke Python threshold re-derivation. Concrete subclasses add
    their own single value field (name/type/unit differs per consumer); this
    base only standardizes the tier FK. A missing row is a content gap for the
    consumer to handle explicitly (see each subclass's docstring), not a crash
    baked into this base.
    """

    outcome_tier = models.OneToOneField(
        "traits.CheckOutcome",
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s",
    )

    class Meta:
        abstract = True
        ordering = ["outcome_tier__success_level"]


class CheckCategory(NaturalKeyMixin, SharedMemoryModel):
    """Grouping for check types (Social, Combat, Exploration, Magic)."""

    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name_plural = "Check categories"

    def __str__(self):
        return self.name


class CheckType(NaturalKeyMixin, SharedMemoryModel):
    """Staff-defined check type with trait and aspect composition."""

    name = models.CharField(max_length=100)
    category = models.ForeignKey(
        CheckCategory,
        on_delete=models.CASCADE,
        related_name="check_types",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name", "category"]
        dependencies = ["checks.CheckCategory"]

    class Meta:
        ordering = ["category__display_order", "display_order", "name"]
        unique_together = ["name", "category"]

    def __str__(self):
        return self.name


class CheckTypeTrait(NaturalKeyMixin, SharedMemoryModel):
    """Weighted trait contribution to a check type."""

    check_type = models.ForeignKey(
        CheckType,
        on_delete=models.CASCADE,
        related_name="traits",
    )
    trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.CASCADE,
        related_name="check_type_traits",
    )
    weight = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0,
        help_text="Multiplier for this trait's contribution (default 1.0)",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["check_type", "trait"]
        dependencies = ["checks.CheckType", "traits.Trait"]

    class Meta:
        unique_together = ["check_type", "trait"]

    def __str__(self):
        return f"{self.check_type.name}: {self.trait.name} ({self.weight}x)"


class CheckTypeAspect(NaturalKeyMixin, SharedMemoryModel):
    """Weighted aspect relevance for a check type."""

    check_type = models.ForeignKey(
        CheckType,
        on_delete=models.CASCADE,
        related_name="aspects",
    )
    aspect = models.ForeignKey(
        "classes.Aspect",
        on_delete=models.CASCADE,
        related_name="check_type_aspects",
    )
    weight = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0,
        help_text="Relevance multiplier for this aspect (default 1.0)",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["check_type", "aspect"]
        dependencies = ["checks.CheckType", "classes.Aspect"]

    class Meta:
        unique_together = ["check_type", "aspect"]

    def __str__(self):
        return f"{self.check_type.name}: {self.aspect.name} ({self.weight}x)"


class CheckTypeSpecialization(NaturalKeyMixin, SharedMemoryModel):
    """Weighted specialization contribution to a check type (#1688).

    The third leg of the standing **stat + skill + specialization** check shape (see
    ``docs/roadmap/design-tenets.md``): the parent skill rides the ordinary ``CheckTypeTrait``
    path (a skill is Trait-backed), and this adds the specialization on top **when the character
    owns it** — ``CharacterSpecializationValue`` is 0 for a non-owner, so a non-specialist simply
    rolls stat + skill. Specialization values scale like skills, so they convert through the same
    ``PointConversionRange`` as a SKILL trait.
    """

    check_type = models.ForeignKey(
        CheckType,
        on_delete=models.CASCADE,
        related_name="specializations",
    )
    specialization = models.ForeignKey(
        "skills.Specialization",
        on_delete=models.CASCADE,
        related_name="check_type_specializations",
    )
    weight = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0,
        help_text="Multiplier for this specialization's contribution (default 1.0)",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["check_type", "specialization"]
        dependencies = ["checks.CheckType", "skills.Specialization"]

    class Meta:
        unique_together = ["check_type", "specialization"]

    def __str__(self):
        return f"{self.check_type.name}: {self.specialization.name} ({self.weight}x)"


# ---------------------------------------------------------------------------
# Generic Consequence system
# ---------------------------------------------------------------------------


class Consequence(SharedMemoryModel):
    """
    A possible outcome tied to a CheckOutcome tier.

    Generic consequence used by any system that maps check results to weighted
    outcomes: challenges, combat, magic, social scenes, etc. Domain-specific
    systems reference Consequence via through models that add context
    (e.g., ChallengeTemplateConsequence adds resolution_type).
    """

    outcome_tier = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.CASCADE,
        related_name="consequences",
    )
    label = models.CharField(max_length=200)
    mechanical_description = models.TextField(blank=True)
    weight = models.PositiveIntegerField(default=1)
    character_loss = models.BooleanField(default=False)
    theater = models.BooleanField(
        default=False,
        help_text=(
            "Authored drama flag (#924): a tier pool containing this "
            "consequence fires the roulette reveal even without a "
            "character_loss candidate (character_loss always fires it)."
        ),
    )

    def __str__(self) -> str:
        return self.label


class ConsequenceEffect(SharedMemoryModel):
    """
    A structured mechanical effect applied when a consequence is selected.

    Each consequence can have zero or more effects, executed in order.
    The effect_type determines which fields are relevant; clean() validates
    that the correct fields are populated.
    """

    consequence = models.ForeignKey(
        Consequence,
        on_delete=models.CASCADE,
        related_name="effects",
    )
    effect_type = models.CharField(
        max_length=32,
        choices=EffectType.choices,
    )
    execution_order = models.PositiveIntegerField(default=0)
    target = models.CharField(
        max_length=20,
        choices=EffectTarget.choices,
        default=EffectTarget.SELF,
    )

    # Condition effects
    condition_template = models.ForeignKey(
        "conditions.ConditionTemplate",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="consequence_effects",
    )
    condition_severity = models.PositiveIntegerField(null=True, blank=True)

    # Relationship-condition effects (#1697) — the directed-allure write side. The flirt/seduce
    # TARGET becomes Attracted To the actor; a null duration is permanent, a set duration creates a
    # temporary (expiring) condition (e.g. Very Attracted). Direction is resolved in the handler.
    relationship_condition = models.ForeignKey(
        "relationships.RelationshipCondition",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="consequence_effects",
    )
    relationship_condition_duration = models.DurationField(null=True, blank=True)

    # Property effects
    property = models.ForeignKey(
        "mechanics.Property",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="consequence_effects",
    )
    property_value = models.PositiveIntegerField(null=True, blank=True)

    # Damage effects (stubbed — needs HP/combat system)
    damage_amount = models.PositiveIntegerField(null=True, blank=True)
    damage_type = models.ForeignKey(
        "conditions.DamageType",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="consequence_effects",
    )

    # Flow effects
    flow_definition = models.ForeignKey(
        "flows.FlowDefinition",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="consequence_effects",
    )

    # Codex effects
    codex_entry = models.ForeignKey(
        "codex.CodexEntry",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="consequence_effects",
    )

    # Legend award effects
    legend_base_value = models.PositiveIntegerField(null=True, blank=True)
    legend_source_type = models.ForeignKey(
        "societies.LegendSourceType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="consequence_effects",
    )
    legend_description_template = models.TextField(blank=True, default="")

    # Capture effects (#931). Both optional: a captor org may be unnamed, and
    # the off-screen-loss flag defaults to the safe "never lost off-screen".
    capture_captor_organization = models.ForeignKey(
        "societies.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capture_consequence_effects",
        help_text="The org that takes the captive (and issues any ransom). Optional.",
    )
    capture_offscreen_loss_allowed = models.BooleanField(
        default=False,
        help_text=(
            "Authored default for the captive's off-screen-loss flag. False keeps"
            " the captive un-loseable while the player is away."
        ),
    )
    # Phase-4 per-capture overrides (#931). Each falls through to the one
    # CaptivityConfig default when left unset, so a marquee captor hand-crafts
    # its own cell + loops here while routine captures use the singleton.
    capture_captive_template = models.ForeignKey(
        "missions.MissionTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Override mission granted to this captive (escape + get-word-out loops)."
            " Unset = the CaptivityConfig default."
        ),
    )
    capture_rescue_template = models.ForeignKey(
        "missions.MissionTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Override rescue mission for this capture. Unset = the CaptivityConfig default.",
    )
    capture_cell_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Override cell room name. Unset = the CaptivityConfig default.",
    )
    capture_cell_description = models.TextField(
        blank=True,
        default="",
        help_text="Override cell room description. Unset = the CaptivityConfig default.",
    )
    capture_clue_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Override rescue-clue name at the capture site. Unset = CaptivityConfig default.",
    )
    capture_clue_description = models.TextField(
        blank=True,
        default="",
        help_text="Override rescue-clue description. Unset = the CaptivityConfig default.",
    )
    capture_clue_detect_difficulty = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Override Search difficulty to spot the rescue clue. Unset = config default.",
    )

    # Positioning / reshaping effects (#1018). Resolved contextually within the
    # actor's room at apply time; no FK to a per-room runtime Position.
    position_name = models.CharField(max_length=50, blank=True, default="")
    position_name_b = models.CharField(max_length=50, blank=True, default="")
    position_kind = models.CharField(
        max_length=20, choices=PositionKind.choices, blank=True, default=""
    )
    position_description = models.TextField(blank=True, default="")
    position_destination = models.CharField(
        max_length=20, choices=PositionDestination.choices, blank=True, default=""
    )
    position_connect_from_actor = models.BooleanField(default=True)
    position_place_occupant = models.BooleanField(default=False)

    class Meta:
        ordering = ["execution_order"]

    def __str__(self) -> str:
        return f"{self.consequence.label}: {self.get_effect_type_display()}"

    # Maps effect_type -> list of (field_name, id_attr) that must be set.
    _REQUIRED_FIELDS: dict[str, list[tuple[str, str]]] = {
        EffectType.APPLY_CONDITION: [("condition_template", "condition_template_id")],
        EffectType.REMOVE_CONDITION: [("condition_template", "condition_template_id")],
        EffectType.SET_RELATIONSHIP_CONDITION: [
            ("relationship_condition", "relationship_condition_id")
        ],
        EffectType.ADD_PROPERTY: [("property", "property_id")],
        EffectType.REMOVE_PROPERTY: [("property", "property_id")],
        EffectType.DEAL_DAMAGE: [
            ("damage_amount", "damage_amount"),
            ("damage_type", "damage_type_id"),
        ],
        EffectType.LAUNCH_ATTACK: [("damage_type", "damage_type_id")],
        EffectType.LAUNCH_FLOW: [("flow_definition", "flow_definition_id")],
        EffectType.GRANT_CODEX: [("codex_entry", "codex_entry_id")],
        EffectType.MAGICAL_SCARS: [("condition_template", "condition_template_id")],
        EffectType.CREATE_POSITION: [("position_name", "position_name")],
        EffectType.SEVER_EDGE: [
            ("position_name", "position_name"),
            ("position_name_b", "position_name_b"),
        ],
        EffectType.CONNECT_EDGE: [
            ("position_name", "position_name"),
            ("position_name_b", "position_name_b"),
        ],
    }

    def clean(self) -> None:
        """Validate that the correct fields are populated for the effect type."""
        errors: dict[str, str] = {}
        self._validate_required_fields(errors)
        if self.effect_type == EffectType.LEGEND_AWARD:
            self._validate_legend_award_fields(errors)
        else:
            self._validate_non_legend_award_fields(errors)
        if self.effect_type == EffectType.MOVE_TO_POSITION:
            self._validate_move_to_position_fields(errors)

        if errors:
            raise ValidationError(errors)

    def _validate_required_fields(self, errors: dict[str, str]) -> None:
        """Populate *errors* for any per-effect-type required field left unset."""
        required = self._REQUIRED_FIELDS.get(self.effect_type, [])
        for field_name, id_attr in required:
            if not getattr(self, id_attr, None):
                errors[field_name] = f"{field_name} is required for {self.effect_type}"

    def _validate_legend_award_fields(self, errors: dict[str, str]) -> None:
        """Populate *errors* for LEGEND_AWARD-required fields left unset/invalid."""
        if not self.legend_base_value or self.legend_base_value <= 0:
            msg = "legend_base_value must be a positive integer for LEGEND_AWARD effects"
            errors["legend_base_value"] = msg
        if not self.legend_source_type_id:
            msg = "legend_source_type is required for LEGEND_AWARD effects"
            errors["legend_source_type"] = msg

    def _validate_non_legend_award_fields(self, errors: dict[str, str]) -> None:
        """Populate *errors* for legend fields that must stay unset off LEGEND_AWARD."""
        if self.legend_base_value is not None:
            msg = "legend_base_value must be null for non-LEGEND_AWARD effects"
            errors["legend_base_value"] = msg
        if self.legend_source_type_id:
            msg = "legend_source_type must be null for non-LEGEND_AWARD effects"
            errors["legend_source_type"] = msg
        if self.legend_description_template:
            msg = "legend_description_template must be blank for non-LEGEND_AWARD effects"
            errors["legend_description_template"] = msg

    def _validate_move_to_position_fields(self, errors: dict[str, str]) -> None:
        """Populate *errors* for MOVE_TO_POSITION-specific required fields."""
        if not self.position_destination:
            errors["position_destination"] = "position_destination is required for MOVE_TO_POSITION"
            return
        if self.position_destination == PositionDestination.NAMED and not self.position_name:
            errors["position_name"] = "position_name is required when destination is NAMED"
