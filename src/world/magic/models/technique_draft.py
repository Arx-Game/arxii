"""TechniqueDraft: per-character work-in-progress technique authoring state.

A TechniqueDraft holds a character's in-progress technique design until they
finalise it via the technique-builder pipeline.  Because a draft is intentionally
incomplete, every design knob is nullable or carries a safe default.

Payload child tables mirror the Technique payloads but point to a draft FK
instead of a Technique FK:

- TechniqueDraftCapabilityGrant  (inherits AbstractCapabilityGrant)
- TechniqueDraftDamageProfile    (inherits AbstractDamageProfile)
- TechniqueDraftAppliedCondition (inherits AbstractAppliedCondition)
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.models.techniques import (
    AbstractAppliedCondition,
    AbstractCapabilityGrant,
    AbstractDamageProfile,
    ConditionTargetKind,
)


class TechniqueDraft(SharedMemoryModel):
    """In-progress technique being authored by a character.

    Intentionally incomplete: every design knob is nullable or defaulted so the
    draft can be saved at any point in the authoring workflow.  There is exactly
    one draft per character (OneToOneField → CharacterSheet).
    """

    character = models.OneToOneField(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="technique_draft",
        help_text="Character who owns this draft.",
    )
    name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Working name for the technique.",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Working description for the technique.",
    )

    # --- design knobs (all nullable/defaulted for partial authoring) ---

    gift = models.ForeignKey(
        "magic.Gift",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="technique_drafts",
        help_text="Gift this technique will belong to.",
    )
    style = models.ForeignKey(
        "magic.TechniqueStyle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="technique_drafts",
        help_text="Technique style (restricted by Path).",
    )
    effect_type = models.ForeignKey(
        "magic.EffectType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="technique_drafts",
        help_text="Type of magical effect.",
    )
    action_category = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text="Physical/social/mental arena (optional until finalised).",
    )
    tier = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Target tier (derived from level at finalisation; stored for UI).",
    )
    intensity = models.PositiveIntegerField(
        default=0,
        help_text="Base power of the technique.",
    )
    control = models.PositiveIntegerField(
        default=0,
        help_text="Base safety/precision.",
    )
    anima_cost = models.PositiveIntegerField(
        default=0,
        help_text="Planned anima cost.",
    )
    restrictions = models.ManyToManyField(
        "magic.Restriction",
        blank=True,
        related_name="technique_drafts",
        help_text="Restrictions applied for power bonuses.",
    )
    consequence_pool = models.ForeignKey(
        "actions.ConsequencePool",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Curated consequence-pool flavor for the resulting technique's "
            "standalone casts. Null = shared default."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Technique Draft"
        verbose_name_plural = "Technique Drafts"

    def __str__(self) -> str:
        label = self.name or "(unnamed)"
        return f"Draft: {label} [{self.character}]"


class TechniqueDraftCapabilityGrant(AbstractCapabilityGrant):
    """A capability grant row belonging to a TechniqueDraft.

    Inherits all data columns from AbstractCapabilityGrant.
    """

    draft = models.ForeignKey(
        TechniqueDraft,
        on_delete=models.CASCADE,
        related_name="capability_grants",
    )

    class Meta:
        verbose_name = "Technique Draft Capability Grant"
        verbose_name_plural = "Technique Draft Capability Grants"

    def __str__(self) -> str:
        return f"{self.draft} grants {self.capability}"


class TechniqueDraftDamageProfile(AbstractDamageProfile):
    """A damage profile row belonging to a TechniqueDraft.

    Inherits all data columns from AbstractDamageProfile.
    """

    draft = models.ForeignKey(
        TechniqueDraft,
        on_delete=models.CASCADE,
        related_name="damage_profiles",
    )

    class Meta:
        verbose_name = "Technique Draft Damage Profile"
        verbose_name_plural = "Technique Draft Damage Profiles"

    def __str__(self) -> str:
        type_str = self.damage_type.name if self.damage_type else "untyped"
        return f"{self.draft} → {self.base_damage} {type_str}"


class TechniqueDraftAppliedCondition(AbstractAppliedCondition):
    """An applied-condition row belonging to a TechniqueDraft.

    Inherits all data columns from AbstractAppliedCondition.
    """

    draft = models.ForeignKey(
        TechniqueDraft,
        on_delete=models.CASCADE,
        related_name="applied_conditions",
    )

    class Meta:
        verbose_name = "Technique Draft Applied Condition"
        verbose_name_plural = "Technique Draft Applied Conditions"

    def __str__(self) -> str:
        return f"{self.draft} → {self.condition} ({self.target_kind})"


class TechniqueDraftRemovedCondition(AbstractAppliedCondition):
    """A removed-condition (dispel) row belonging to a TechniqueDraft.

    Mirrors ``TechniqueRemovedCondition`` for the draft workbench. Inherits all data
    columns from ``AbstractAppliedCondition``; the severity/duration/stack knobs are
    inert (enforced on the committed row's ``clean()``). Adds ``remove_all_stacks``.
    """

    draft = models.ForeignKey(
        TechniqueDraft,
        on_delete=models.CASCADE,
        related_name="removed_conditions",
    )
    remove_all_stacks = models.BooleanField(
        default=True,
        help_text=(
            "If True, all stacks of the condition are removed. If False, only one "
            "stack is decremented."
        ),
    )

    class Meta:
        verbose_name = "Technique Draft Removed Condition"
        verbose_name_plural = "Technique Draft Removed Conditions"

    def __str__(self) -> str:
        return f"{self.draft} → removes {self.condition} ({self.target_kind})"


class TechniqueDraftTreatment(SharedMemoryModel):
    """A treatment payload row belonging to a TechniqueDraft.

    Mirrors ``TechniqueTreatment`` for the draft workbench. Points at a
    TreatmentTemplate; on author, the technique-cast path calls
    perform_treatment with the caster as helper.
    """

    draft = models.ForeignKey(
        TechniqueDraft,
        on_delete=models.CASCADE,
        related_name="treatments",
    )
    treatment_template = models.ForeignKey(
        "conditions.TreatmentTemplate",
        on_delete=models.PROTECT,
        related_name="draft_technique_payloads",
    )
    target_kind = models.CharField(
        max_length=16,
        choices=ConditionTargetKind.choices,
        default=ConditionTargetKind.ALLY,
    )
    minimum_success_level = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Technique Draft Treatment"
        verbose_name_plural = "Technique Draft Treatments"

    def __str__(self) -> str:
        return f"{self.draft} → treats {self.treatment_template.name} ({self.target_kind})"
