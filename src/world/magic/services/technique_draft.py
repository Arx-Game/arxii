"""Draft-based technique authoring services (#1496).

These functions manage the per-character TechniqueDraft work-in-progress state
and convert a complete draft into a TechniqueDesignInput for the builder pipeline.

Design notes:
- Callers resolve names → model instances before calling here.  These services
  accept resolved instances/values and return model instances, never dicts.
- draft_to_design is the boundary point: it validates completeness and converts
  to the immutable TechniqueDesignInput frozen dataclass.
- validate_design_for_character (in technique_builder.py) is the shared player
  gate; call it after draft_to_design when finalising via telnet or web.
"""

from __future__ import annotations

from decimal import Decimal

from world.magic.exceptions import NoActiveTechniqueDraft, TechniqueDraftIncomplete
from world.magic.models import (
    TechniqueDraft,
    TechniqueDraftAppliedCondition,
    TechniqueDraftCapabilityGrant,
    TechniqueDraftDamageProfile,
    TechniqueDraftMoraleEffect,
    TechniqueDraftRemovedCondition,
    TechniqueDraftTreatment,
)
from world.magic.services.technique_builder import get_technique_tier_budget
from world.magic.types.technique_builder import (
    AppliedConditionSpec,
    CapabilityGrantSpec,
    DamageProfileSpec,
    MoraleEffectSpec,
    RemovedConditionSpec,
    TechniqueDesignInput,
    TreatmentSpec,
)
from world.vitals.constants import NEVER_TO_FULL_FRACTION

# =============================================================================
# Draft lifecycle
# =============================================================================


def get_or_start_draft(character) -> TechniqueDraft:
    """Return the character's existing draft, or create a blank one."""
    draft, _ = TechniqueDraft.objects.get_or_create(character=character)
    return draft


def start_technique_draft(character, *, name: str) -> TechniqueDraft:
    """Replace any existing draft with a fresh one named ``name``."""
    TechniqueDraft.objects.filter(character=character).delete()
    return TechniqueDraft.objects.create(character=character, name=name)


def get_active_draft(character) -> TechniqueDraft:
    """Return the character's current draft or raise ``NoActiveTechniqueDraft``."""
    try:
        return TechniqueDraft.objects.get(character=character)
    except TechniqueDraft.DoesNotExist:
        raise NoActiveTechniqueDraft from None


def discard_draft(character) -> None:
    """Delete the character's current draft (no-op if absent)."""
    TechniqueDraft.objects.filter(character=character).delete()


# =============================================================================
# Field updates
# =============================================================================


def set_draft_fields(draft: TechniqueDraft, **fields) -> TechniqueDraft:
    """Update arbitrary scalar or FK knobs on the draft and save.

    Callers pass resolved model instances for FK fields (gift=, effect_type=, etc.).
    Returns the updated draft instance.
    """
    for key, value in fields.items():
        setattr(draft, key, value)
    draft.save()
    return draft


# =============================================================================
# Restriction M2M
# =============================================================================


def add_draft_restriction(draft: TechniqueDraft, restriction) -> None:
    """Add a Restriction to the draft's M2M set (idempotent via Django M2M)."""
    draft.restrictions.add(restriction)


def remove_draft_restriction(draft: TechniqueDraft, restriction) -> None:
    """Remove a Restriction from the draft's M2M set."""
    draft.restrictions.remove(restriction)


# =============================================================================
# Payload children — capability grants
# =============================================================================


def add_draft_capability_grant(
    draft: TechniqueDraft,
    *,
    capability,
    base_value: int,
    intensity_multiplier: float,
) -> TechniqueDraftCapabilityGrant:
    """Append a capability grant row to the draft and return it."""
    return TechniqueDraftCapabilityGrant.objects.create(
        draft=draft,
        capability=capability,
        base_value=base_value,
        intensity_multiplier=intensity_multiplier,
    )


def remove_draft_capability_grant(row_id: int) -> None:
    """Delete a TechniqueDraftCapabilityGrant row by primary key."""
    TechniqueDraftCapabilityGrant.objects.filter(pk=row_id).delete()


# =============================================================================
# Payload children — damage profiles
# =============================================================================


# A draft damage row exposes each independently authored profile property.
def add_draft_damage_profile(  # noqa: PLR0913
    draft: TechniqueDraft,
    *,
    damage_type,
    base_damage: int,
    damage_intensity_multiplier: float,
    ignores_soak: bool = False,
    resistance_shift: int = 0,
    bypasses_wards: bool = False,
) -> TechniqueDraftDamageProfile:
    """Append a damage profile row to the draft and return it."""
    return TechniqueDraftDamageProfile.objects.create(
        draft=draft,
        damage_type=damage_type,
        base_damage=base_damage,
        damage_intensity_multiplier=damage_intensity_multiplier,
        ignores_soak=ignores_soak,
        resistance_shift=resistance_shift,
        bypasses_wards=bypasses_wards,
    )


def remove_draft_damage_profile(row_id: int) -> None:
    """Delete a TechniqueDraftDamageProfile row by primary key."""
    TechniqueDraftDamageProfile.objects.filter(pk=row_id).delete()


# =============================================================================
# Payload children — applied conditions
# =============================================================================


def add_draft_applied_condition(
    draft: TechniqueDraft,
    *,
    condition,
    base_severity: int = 1,
    base_duration_rounds: int | None = None,
) -> TechniqueDraftAppliedCondition:
    """Append an applied condition row to the draft and return it."""
    return TechniqueDraftAppliedCondition.objects.create(
        draft=draft,
        condition=condition,
        base_severity=base_severity,
        base_duration_rounds=base_duration_rounds,
    )


def remove_draft_applied_condition(row_id: int) -> None:
    """Delete a TechniqueDraftAppliedCondition row by primary key."""
    TechniqueDraftAppliedCondition.objects.filter(pk=row_id).delete()


# =============================================================================
# Payload children — removed conditions (dispel/cleanse, #1585)
# =============================================================================


def add_draft_removed_condition(
    draft: TechniqueDraft,
    *,
    condition,
    target_kind: str = "enemy",
    minimum_success_level: int = 1,
    remove_all_stacks: bool = True,
) -> TechniqueDraftRemovedCondition:
    """Append a removed-condition (dispel) row to the draft and return it."""
    return TechniqueDraftRemovedCondition.objects.create(
        draft=draft,
        condition=condition,
        target_kind=target_kind,
        minimum_success_level=minimum_success_level,
        remove_all_stacks=remove_all_stacks,
    )


def remove_draft_removed_condition(row_id: int) -> None:
    """Delete a TechniqueDraftRemovedCondition row by primary key."""
    TechniqueDraftRemovedCondition.objects.filter(pk=row_id).delete()


def add_draft_treatment(
    draft: TechniqueDraft,
    *,
    treatment_template,
    target_kind: str = "ally",
    minimum_success_level: int = 1,
    mend_cap_fraction: Decimal = NEVER_TO_FULL_FRACTION,
) -> TechniqueDraftTreatment:
    """Append a treatment payload row to the draft and return it.

    ``mend_cap_fraction`` (#4600) is how far the technique may heal a wound, as a
    share of its damage; it defaults to the never-to-full ceiling.
    """
    return TechniqueDraftTreatment.objects.create(
        draft=draft,
        treatment_template=treatment_template,
        target_kind=target_kind,
        minimum_success_level=minimum_success_level,
        mend_cap_fraction=mend_cap_fraction,
    )


def remove_draft_treatment(row_id: int) -> None:
    """Delete a TechniqueDraftTreatment row by primary key."""
    TechniqueDraftTreatment.objects.filter(pk=row_id).delete()


def set_draft_morale_effect(
    draft: TechniqueDraft,
    *,
    base_morale: int,
    morale_intensity_multiplier: Decimal = Decimal(0),
    morale_per_extra_sl: int = 0,
    minimum_success_level: int = 1,
) -> TechniqueDraftMoraleEffect:
    """Set the draft's one morale row (#4619), replacing any earlier one."""
    row, _created = TechniqueDraftMoraleEffect.objects.update_or_create(
        draft=draft,
        defaults={
            "base_morale": base_morale,
            "morale_intensity_multiplier": morale_intensity_multiplier,
            "morale_per_extra_sl": morale_per_extra_sl,
            "minimum_success_level": minimum_success_level,
        },
    )
    return row


def clear_draft_morale_effect(draft: TechniqueDraft) -> None:
    """Remove the draft's morale row, if it has one (#4619)."""
    TechniqueDraftMoraleEffect.objects.filter(draft=draft).delete()


# =============================================================================
# draft → design conversion
# =============================================================================


def draft_to_design(draft: TechniqueDraft) -> TechniqueDesignInput:
    """Convert a complete TechniqueDraft to a TechniqueDesignInput.

    Derives ``level`` from the tier's ``representative_level`` (mirroring
    the serializer at serializers.py:3073).

    Raises:
        TechniqueDraftIncomplete: when one or more required knobs are unset,
            listing every missing field name in ``exc.missing_fields``.
    """
    missing: list[str] = []
    if not draft.name:
        missing.append("name")
    if draft.gift_id is None:
        missing.append("gift")
    if draft.effect_type_id is None:
        missing.append("effect_type")
    if not draft.action_category:
        missing.append("action_category")
    if draft.tier is None:
        missing.append("tier")
    if missing:
        raise TechniqueDraftIncomplete(missing)

    level = get_technique_tier_budget(draft.tier).representative_level  # type: ignore[arg-type]

    morale_row = TechniqueDraftMoraleEffect.objects.filter(draft=draft).first()
    morale_effect = (
        MoraleEffectSpec(
            minimum_success_level=morale_row.minimum_success_level,
            base_morale=morale_row.base_morale,
            morale_intensity_multiplier=float(morale_row.morale_intensity_multiplier),
            morale_per_extra_sl=morale_row.morale_per_extra_sl,
        )
        if morale_row is not None
        else None
    )

    return TechniqueDesignInput(
        name=draft.name,
        description=draft.description,
        gift_id=draft.gift_id,  # type: ignore[arg-type]
        effect_type_id=draft.effect_type_id,  # type: ignore[arg-type]
        action_category=draft.action_category,
        tier=draft.tier,  # type: ignore[arg-type]
        intensity=draft.intensity,
        control=draft.control,
        anima_cost=draft.anima_cost,
        level=level,
        restriction_ids=tuple(draft.restrictions.values_list("id", flat=True)),
        capability_grants=tuple(
            CapabilityGrantSpec(
                capability_id=row.capability_id,
                base_value=row.base_value,
                intensity_multiplier=float(row.intensity_multiplier),
            )
            for row in draft.capability_grants.all()
        ),
        damage_profiles=tuple(
            DamageProfileSpec(
                damage_type_id=row.damage_type_id,
                base_damage=row.base_damage,
                damage_intensity_multiplier=float(row.damage_intensity_multiplier),
                ignores_soak=row.ignores_soak,
                resistance_shift=row.resistance_shift,
                bypasses_wards=row.bypasses_wards,
            )
            for row in draft.damage_profiles.all()
        ),
        applied_conditions=tuple(
            AppliedConditionSpec(
                condition_id=row.condition_id,
                base_severity=row.base_severity,
                base_duration_rounds=row.base_duration_rounds,
            )
            for row in draft.applied_conditions.all()
        ),
        removed_conditions=tuple(
            RemovedConditionSpec(
                condition_id=row.condition_id,
                target_kind=row.target_kind,
                minimum_success_level=row.minimum_success_level,
                remove_all_stacks=row.remove_all_stacks,
            )
            for row in draft.removed_conditions.all()
        ),
        treatments=tuple(
            TreatmentSpec(
                treatment_template_id=row.treatment_template_id,
                target_kind=row.target_kind,
                minimum_success_level=row.minimum_success_level,
                mend_cap_fraction=row.mend_cap_fraction,
            )
            for row in draft.treatments.all()
        ),
        morale_effect=morale_effect,
        consequence_pool_id=draft.consequence_pool_id,
    )
