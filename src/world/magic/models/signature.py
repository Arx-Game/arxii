"""SignatureMotifBonus catalog model + payload child rows (#1582).

A SignatureMotifBonus is a staff-authored, facet/resonance-gated, additive bonus
that a player may select when signing a technique. It carries the same effect-payload
child rows (capability grants, damage profiles, applied conditions) as Technique /
TechniqueVariant, reusing the Abstract* bases from techniques.py.

Design boundary: SignatureMotifBonus is NOT a TechniqueVariant. It must NOT inherit
AbstractSpecializedVariant and must NOT participate in the crossing ceremony
(`execute_crossing_ceremonies`, formerly `fire_variant_discoveries`). It is an
additive flourish, not a discovered variant.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.models.motifs import Facet, Motif, MotifResonanceAssociation
from world.magic.models.techniques import (
    AbstractAppliedCondition,
    AbstractCapabilityGrant,
    AbstractDamageProfile,
)


class SignatureMotifBonus(SharedMemoryModel):
    """Staff-authored bonus available to a signed technique when the character's
    Motif satisfies the required facet and/or resonance gate.

    At least one of ``required_facet`` / ``required_resonance`` must be set
    (enforced by ``clean()``).  When both are set, both gates must pass (AND
    semantics).

    ``flat_intensity_delta`` is the additive modifier applied to the signed
    technique's effective intensity when this bonus is active.
    """

    name = models.CharField(
        max_length=200,
        help_text="Descriptive name for this bonus (staff-facing label).",
    )
    narrative_snippet = models.TextField(
        blank=True,
        help_text=(
            "Short cosmetic prose shown to the player when the bonus activates "
            "(e.g., 'Your strikes carry the hungering edge of the wolf.')."
        ),
    )
    required_facet = models.ForeignKey(
        Facet,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="signature_bonuses",
        help_text=(
            "The Motif must contain a MotifResonanceAssociation with this facet "
            "for the bonus to qualify."
        ),
    )
    required_resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="signature_bonuses",
        help_text=(
            "The Motif must have a MotifResonance for this resonance for the bonus to qualify."
        ),
    )
    flat_intensity_delta = models.SmallIntegerField(
        default=0,
        help_text="Flat modifier added to the signed technique's effective intensity.",
    )

    class Meta:
        verbose_name = "Signature Motif Bonus"
        verbose_name_plural = "Signature Motif Bonuses"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        """Validate that at least one gate field is set."""
        if not self.required_facet_id and not self.required_resonance_id:
            msg = "At least one of 'required_facet' or 'required_resonance' must be set."
            raise ValidationError(msg)

    # ------------------------------------------------------------------
    # Payload cached accessors (mirror TechniqueVariant's pattern)
    # ------------------------------------------------------------------

    @cached_property
    def cached_capability_grants(self) -> list:
        """Capability grants for this bonus. Supports Prefetch(to_attr=).

        To invalidate: ``del instance.cached_capability_grants``.
        """
        return list(self.capability_grants.all())

    @cached_property
    def cached_damage_profiles(self) -> list:
        """Damage profiles for this bonus. Supports Prefetch(to_attr=).

        To invalidate: ``del instance.cached_damage_profiles``.
        """
        return list(self.damage_profiles.select_related("damage_type").all())

    @cached_property
    def cached_condition_applications(self) -> list:
        """Applied conditions for this bonus. Supports Prefetch(to_attr=).

        To invalidate: ``del instance.cached_condition_applications``.
        """
        return list(self.condition_applications.select_related("condition__category").all())

    # ------------------------------------------------------------------
    # Gate predicate
    # ------------------------------------------------------------------

    def qualifies_for(self, character_sheet) -> bool:
        """Return True iff the character's Motif satisfies this bonus's gate.

        Rules (AND semantics — every set gate must pass):
        - ``required_resonance`` set → Motif must have a MotifResonance row for that resonance.
        - ``required_facet`` set → Motif must have a MotifResonanceAssociation whose facet_id
          matches exactly (hierarchy descent is deferred — not implemented here).

        Returns False when the character has no Motif (Motif.DoesNotExist).
        """
        try:
            motif = character_sheet.motif
        except Motif.DoesNotExist:
            return False

        if self.required_resonance_id is not None:
            if not motif.resonances.filter(resonance_id=self.required_resonance_id).exists():
                return False

        if self.required_facet_id is not None:
            if not MotifResonanceAssociation.objects.filter(
                motif_resonance__motif=motif,
                facet_id=self.required_facet_id,
            ).exists():
                return False

        return True


# ---------------------------------------------------------------------------
# Payload child rows
# ---------------------------------------------------------------------------


class SignatureMotifBonusCapabilityGrant(AbstractCapabilityGrant):
    """Capability granted by a SignatureMotifBonus (mirrors TechniqueVariantCapabilityGrant)."""

    signature_bonus = models.ForeignKey(
        SignatureMotifBonus,
        on_delete=models.CASCADE,
        related_name="capability_grants",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["signature_bonus", "capability"],
                name="sig_bonus_cap_grant_unique",
            ),
        ]


class SignatureMotifBonusDamageProfile(AbstractDamageProfile):
    """Damage profile for a SignatureMotifBonus (mirrors TechniqueVariantDamageProfile)."""

    signature_bonus = models.ForeignKey(
        SignatureMotifBonus,
        on_delete=models.CASCADE,
        related_name="damage_profiles",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["signature_bonus", "damage_type"],
                condition=models.Q(damage_type__isnull=False),
                name="sig_bonus_damage_profile_per_type",
            ),
            models.UniqueConstraint(
                fields=["signature_bonus"],
                condition=models.Q(damage_type__isnull=True),
                name="sig_bonus_untyped_damage_profile",
            ),
        ]


class SignatureMotifBonusAppliedCondition(AbstractAppliedCondition):
    """Applied condition for a SignatureMotifBonus (mirrors TechniqueVariantAppliedCondition)."""

    signature_bonus = models.ForeignKey(
        SignatureMotifBonus,
        on_delete=models.CASCADE,
        related_name="condition_applications",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["signature_bonus", "condition", "target_kind"],
                name="sig_bonus_applied_condition_unique",
            ),
        ]
