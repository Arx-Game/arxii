"""Magical alterations (Mage Scars).

MagicalAlterationTemplate is the authored template for a Mage Scar, layered
on top of a ConditionTemplate. PendingAlteration is a Mage Scar owed to a
character awaiting resolution. MagicalAlterationEvent is the audit record.

Class and table names retain the "MagicalAlteration" prefix for DB
stability; the player-facing label is "Mage Scar".
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.constants import AlterationKind, AlterationTier, PendingAlterationStatus
from world.magic.models.affinity import Affinity, Resonance
from world.magic.models.techniques import Technique


class MagicalAlterationTemplate(SharedMemoryModel):
    """Template for a Mage Scar (permanent magical alteration).

    Mage-specific metadata layered on top of a ConditionTemplate. A Mage
    Scar IS a condition — runtime effects (check modifiers, capability
    effects, resistance, properties, descriptions) live on the OneToOne'd
    ConditionTemplate. This table adds authoring slots, tier classification,
    and origin context.

    Note: the class and table names retain the "MagicalAlteration" prefix
    for database stability; the player-facing label is "Mage Scar".
    """

    condition_template = models.OneToOneField(
        "conditions.ConditionTemplate",
        on_delete=models.CASCADE,
        related_name="magical_alteration",
    )
    tier = models.PositiveSmallIntegerField(
        choices=AlterationTier.choices,
        help_text="Severity tier 1 (cosmetic) through 5 (body partially remade).",
    )
    origin_affinity = models.ForeignKey(
        Affinity,
        on_delete=models.PROTECT,
        related_name="alteration_templates",
        help_text="Which affinity (Celestial/Primal/Abyssal) caused this.",
    )
    origin_resonance = models.ForeignKey(
        Resonance,
        on_delete=models.PROTECT,
        related_name="alteration_templates",
        help_text="The resonance channeled at overburn.",
    )
    weakness_damage_type = models.ForeignKey(
        "conditions.DamageType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="alteration_weaknesses",
        help_text="Damage type the character is now vulnerable to.",
    )
    weakness_magnitude = models.PositiveSmallIntegerField(
        default=0,
        help_text="Vulnerability magnitude, tier-bounded.",
    )
    resonance_bonus_magnitude = models.PositiveSmallIntegerField(
        default=0,
        help_text="Bonus when channeling origin_resonance, tier-bounded.",
    )
    social_reactivity_magnitude = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Reaction strength from magic-phobic observers. Calibrated as "
            "situational world-friction, not character-concept blocker."
        ),
    )
    is_visible_at_rest = models.BooleanField(
        default=False,
        help_text="Shows through normal clothing? Required True at tier 4+.",
    )
    authored_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_alterations",
        help_text="Account that authored this. NULL = system/staff seed.",
    )
    parent_template = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="variants",
        help_text="If spun off from a library entry or prior alteration.",
    )
    is_library_entry = models.BooleanField(
        default=False,
        help_text=(
            "If True, shown to players browsing tier-matched alterations. "
            "Only staff can set this flag."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    kind = models.CharField(
        max_length=24,
        choices=AlterationKind.choices,
        default=AlterationKind.MAGE_SCAR,
        help_text="Discriminator: MAGE_SCAR (Scope 5) vs CORRUPTION_TWIST (Scope 7).",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="corruption_twist_templates",
        help_text="Required for CORRUPTION_TWIST; null for MAGE_SCAR.",
    )
    stage_threshold = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Required for CORRUPTION_TWIST; null for MAGE_SCAR. Range 1-5.",
    )

    class Meta:
        verbose_name = "mage scar"
        verbose_name_plural = "mage scars"
        constraints = [
            models.CheckConstraint(
                name="alteration_template_mage_scar_shape",
                check=(
                    Q(kind=AlterationKind.MAGE_SCAR)
                    & Q(resonance__isnull=True)
                    & Q(stage_threshold__isnull=True)
                )
                | ~Q(kind=AlterationKind.MAGE_SCAR),
            ),
            models.CheckConstraint(
                name="alteration_template_corruption_twist_shape",
                check=(
                    Q(kind=AlterationKind.CORRUPTION_TWIST)
                    & Q(resonance__isnull=False)
                    & Q(stage_threshold__isnull=False)
                )
                | ~Q(kind=AlterationKind.CORRUPTION_TWIST),
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.kind == AlterationKind.MAGE_SCAR:
            if self.resonance is not None or self.stage_threshold is not None:
                msg = "MAGE_SCAR templates must not specify resonance/stage_threshold."
                raise ValidationError(msg)
        elif self.kind == AlterationKind.CORRUPTION_TWIST:
            if self.resonance is None or self.stage_threshold is None:
                msg = "CORRUPTION_TWIST templates require resonance AND stage_threshold."
                raise ValidationError(msg)

    def __str__(self) -> str:
        return f"{self.condition_template.name} (Tier {self.tier})"


class PendingAlteration(SharedMemoryModel):
    """A Mage Scar owed to a character, awaiting resolution.

    Created by the MAGICAL_SCARS effect handler. Blocks progression
    spending until resolved via library browse or author-from-scratch.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="pending_alterations",
    )
    status = models.CharField(
        max_length=20,
        choices=PendingAlterationStatus.choices,
        default=PendingAlterationStatus.OPEN,
    )
    tier = models.PositiveSmallIntegerField(
        choices=AlterationTier.choices,
        help_text=(
            "Required tier for resolved alteration. Upgradeable via same-scene escalation only."
        ),
    )
    triggering_scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_alterations",
    )
    triggering_technique = models.ForeignKey(
        Technique,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    triggering_intensity = models.IntegerField(null=True, blank=True)
    triggering_control = models.IntegerField(null=True, blank=True)
    triggering_anima_cost = models.IntegerField(null=True, blank=True)
    triggering_anima_deficit = models.IntegerField(null=True, blank=True)
    triggering_soulfray_stage = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    audere_active = models.BooleanField(default=False)
    origin_affinity = models.ForeignKey(
        Affinity,
        on_delete=models.PROTECT,
        related_name="pending_alteration_origins",
    )
    origin_resonance = models.ForeignKey(
        Resonance,
        on_delete=models.PROTECT,
        related_name="pending_alteration_origins",
    )
    resolved_alteration = models.ForeignKey(
        MagicalAlterationTemplate,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="resolved_pending",
        help_text="Set when player picks/authors a template.",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_pending_alterations",
    )
    notes = models.TextField(
        blank=True,
        help_text="Staff notes (e.g. reason for staff clear).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "pending mage scar"
        verbose_name_plural = "pending mage scars"
        indexes = [
            models.Index(fields=["character", "status"], name="magic_pendi_charact_4fea0a_idx"),
        ]

    def __str__(self) -> str:
        return f"Pending Tier {self.tier} mage scar for {self.character} ({self.status})"


class MagicalAlterationEvent(SharedMemoryModel):
    """Audit record: this character received this alteration at this moment.

    Created when a PendingAlteration resolves. Survives independently of
    the PendingAlteration and the ConditionInstance.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="alteration_events",
    )
    alteration_template = models.ForeignKey(
        MagicalAlterationTemplate,
        on_delete=models.PROTECT,
        related_name="application_events",
    )
    active_condition = models.ForeignKey(
        "conditions.ConditionInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alteration_events",
    )
    triggering_scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    triggering_technique = models.ForeignKey(
        Technique,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    triggering_intensity = models.IntegerField(null=True, blank=True)
    triggering_control = models.IntegerField(null=True, blank=True)
    triggering_anima_cost = models.IntegerField(null=True, blank=True)
    triggering_anima_deficit = models.IntegerField(null=True, blank=True)
    triggering_soulfray_stage = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    audere_active = models.BooleanField(default=False)
    applied_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(
        blank=True,
        help_text="Freeform staff/system notes.",
    )

    def __str__(self) -> str:
        return (
            f"{self.alteration_template.condition_template.name} "
            f"applied to {self.character} at {self.applied_at}"
        )
