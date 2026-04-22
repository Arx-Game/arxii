"""Magical alteration (Mage Scar) service functions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.magic.constants import (
    ALTERATION_TIER_CAPS,
    MIN_ALTERATION_DESCRIPTION_LENGTH,
    AlterationTier,
    PendingAlterationStatus,
)
from world.magic.models import (
    MagicalAlterationEvent,
    MagicalAlterationTemplate,
    PendingAlteration,
)
from world.magic.types import (
    AlterationResolutionError,
    AlterationResolutionResult,
    PendingAlterationResult,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia.accounts.models import AccountDB

    from world.character_sheets.models import CharacterSheet
    from world.conditions.models import ConditionCategory, DamageType
    from world.magic.models import (
        Affinity,
        Resonance as ResonanceModel,
        Technique,
    )
    from world.scenes.models import Scene


def create_pending_alteration(  # noqa: PLR0913 — kw-only snapshot fields are intentional
    *,
    character: CharacterSheet,
    tier: int,
    origin_affinity: Affinity,
    origin_resonance: ResonanceModel,
    scene: Scene | None,
    triggering_technique: Technique | None = None,
    triggering_intensity: int | None = None,
    triggering_control: int | None = None,
    triggering_anima_cost: int | None = None,
    triggering_anima_deficit: int | None = None,
    triggering_soulfray_stage: int | None = None,
    audere_active: bool = False,
) -> PendingAlterationResult:
    """Create or escalate a PendingAlteration for a character.

    Same-scene dedup: if an OPEN pending exists for the same character +
    scene, upgrade its tier if the new tier is higher. Otherwise no-op.
    Different scenes (or scene=None) always create new pendings.
    """
    from world.magic.constants import PendingAlterationStatus  # noqa: PLC0415
    from world.magic.models import PendingAlteration  # noqa: PLC0415

    snapshot_fields = {
        "triggering_technique": triggering_technique,
        "triggering_intensity": triggering_intensity,
        "triggering_control": triggering_control,
        "triggering_anima_cost": triggering_anima_cost,
        "triggering_anima_deficit": triggering_anima_deficit,
        "triggering_soulfray_stage": triggering_soulfray_stage,
        "audere_active": audere_active,
    }

    if scene is not None:
        existing = PendingAlteration.objects.filter(
            character=character,
            triggering_scene=scene,
            status=PendingAlterationStatus.OPEN,
        ).first()

        if existing is not None:
            if tier > existing.tier:
                previous_tier = existing.tier
                existing.tier = tier
                for field_name, value in snapshot_fields.items():
                    setattr(existing, field_name, value)
                existing.save()
                return PendingAlterationResult(
                    pending=existing,
                    created=False,
                    previous_tier=previous_tier,
                )
            return PendingAlterationResult(
                pending=existing,
                created=False,
                previous_tier=None,
            )

    pending = PendingAlteration.objects.create(
        character=character,
        tier=tier,
        origin_affinity=origin_affinity,
        origin_resonance=origin_resonance,
        triggering_scene=scene,
        **snapshot_fields,
    )
    return PendingAlterationResult(
        pending=pending,
        created=True,
        previous_tier=None,
    )


def _alteration_tier_label(value: object) -> str:
    """Render an alteration tier as its human label, falling back to the raw value."""
    try:
        return AlterationTier(value).label
    except (ValueError, TypeError):
        return str(value)


def validate_alteration_resolution(  # noqa: PLR0912,PLR0913,C901 — sequential validation gates, kw-only args
    *,
    pending_tier: int,
    pending_affinity_id: int,
    pending_resonance_id: int,
    payload: dict,
    is_staff: bool,
    character_sheet: CharacterSheet | None = None,
) -> list[str]:
    """Validate a resolution payload against the pending's tier and origin.

    Returns a list of error strings. Empty list = valid.
    character_sheet is required for library duplicate checks.

    Two distinct paths:
    - Library path (library_entry_pk present): validates tier/affinity/resonance match and
      duplicate check only. All scratch-path checks are skipped — the library entry was
      already validated when authored.
    - Scratch path (no library_entry_pk): validates all tier, magnitude, description, and
      visibility constraints.
    """
    errors: list[str] = []
    library_pk = payload.get("library_entry_pk")

    if library_pk:
        # Library use-as-is path — minimal checks only.
        if character_sheet is None:
            errors.append("character_sheet is required to validate library_entry_pk.")
        else:
            from world.conditions.models import ConditionInstance  # noqa: PLC0415

            library_entry = MagicalAlterationTemplate.objects.filter(
                pk=library_pk,
                is_library_entry=True,
            ).first()
            if library_entry is None:
                errors.append("Library entry not found or not a library entry.")
            else:
                if library_entry.tier != pending_tier:
                    errors.append(
                        f"Library entry tier {_alteration_tier_label(library_entry.tier)} "
                        f"does not match pending tier {_alteration_tier_label(pending_tier)}."
                    )
                if library_entry.origin_affinity_id != pending_affinity_id:
                    errors.append(
                        "Library entry origin affinity does not match the pending alteration."
                    )
                if library_entry.origin_resonance_id != pending_resonance_id:
                    errors.append(
                        "Library entry origin resonance does not match the pending alteration."
                    )
                if ConditionInstance.objects.filter(
                    target=character_sheet.character,
                    condition=library_entry.condition_template,
                ).exists():
                    errors.append("Character already has this condition active.")
        return errors

    # Scratch path — validate all tier, magnitude, description, and visibility constraints.
    tier = payload.get("tier")
    caps = ALTERATION_TIER_CAPS.get(pending_tier, {})

    if tier != pending_tier:
        errors.append(
            f"Tier mismatch: payload tier {_alteration_tier_label(tier)} "
            f"!= pending tier {_alteration_tier_label(pending_tier)}."
        )

    if payload.get("origin_affinity_id") != pending_affinity_id:
        errors.append("Origin affinity does not match the pending alteration.")

    if payload.get("origin_resonance_id") != pending_resonance_id:
        errors.append("Origin resonance does not match the pending alteration.")

    weakness = payload.get("weakness_magnitude", 0)
    if weakness > caps.get("weakness_cap", 0):
        errors.append(
            f"Weakness magnitude {weakness} exceeds tier {pending_tier} cap "
            f"of {caps.get('weakness_cap', 0)}."
        )
    if weakness > 0 and not payload.get("weakness_damage_type_id"):
        errors.append("weakness_damage_type is required when weakness_magnitude > 0.")

    resonance = payload.get("resonance_bonus_magnitude", 0)
    if resonance > caps.get("resonance_cap", 0):
        errors.append(
            f"Resonance bonus magnitude {resonance} exceeds tier {pending_tier} cap "
            f"of {caps.get('resonance_cap', 0)}."
        )

    social = payload.get("social_reactivity_magnitude", 0)
    if social > caps.get("social_cap", 0):
        errors.append(
            f"Social reactivity magnitude {social} exceeds tier {pending_tier} cap "
            f"of {caps.get('social_cap', 0)}."
        )

    if caps.get("visibility_required") and not payload.get("is_visible_at_rest"):
        errors.append(f"is_visible_at_rest must be True at tier {pending_tier}.")

    for field in ("player_description", "observer_description"):
        value = payload.get(field, "")
        if len(value) < MIN_ALTERATION_DESCRIPTION_LENGTH:
            errors.append(
                f"{field} must be at least {MIN_ALTERATION_DESCRIPTION_LENGTH} characters "
                f"(got {len(value)})."
            )

    if payload.get("is_library_entry") and not is_staff:
        errors.append("Only staff can create library entries.")

    return errors


def get_library_entries(
    *,
    tier: int,
    character_affinity_id: int | None = None,
) -> QuerySet[MagicalAlterationTemplate]:
    """Return library entries matching the given tier.

    Sorted: matching origin_affinity first, then everything else, then by name.
    """
    from django.db.models import Case, Value, When  # noqa: PLC0415

    qs = MagicalAlterationTemplate.objects.filter(
        is_library_entry=True,
        tier=tier,
    ).select_related(
        "condition_template",
        "origin_affinity",
        "origin_resonance",
    )
    if character_affinity_id is not None:
        qs = qs.annotate(
            affinity_match=Case(
                When(origin_affinity_id=character_affinity_id, then=Value(0)),
                default=Value(1),
            ),
        ).order_by("affinity_match", "condition_template__name")
    else:
        qs = qs.order_by("condition_template__name")
    return qs


@transaction.atomic
def resolve_pending_alteration(  # noqa: PLR0913 — kw-only resolution fields are intentional
    *,
    pending: PendingAlteration,
    name: str,
    player_description: str,
    observer_description: str,
    weakness_damage_type: DamageType | None = None,
    weakness_magnitude: int = 0,
    resonance_bonus_magnitude: int = 0,
    social_reactivity_magnitude: int = 0,
    is_visible_at_rest: bool,
    resolved_by: AccountDB | None,
    parent_template: MagicalAlterationTemplate | None = None,
    is_library_entry: bool = False,
    library_template: MagicalAlterationTemplate | None = None,
) -> AlterationResolutionResult:
    """Resolve a PendingAlteration by creating or selecting a template.

    If library_template is provided, use it directly (use-as-is path).
    Otherwise create a new ConditionTemplate + MagicalAlterationTemplate.
    In both cases: apply the condition, create the event, mark resolved.
    """
    # Lock the pending row to prevent concurrent double-resolution.
    pending = PendingAlteration.objects.select_for_update().get(pk=pending.pk)
    if pending.status != PendingAlterationStatus.OPEN:
        raise AlterationResolutionError

    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import (  # noqa: PLC0415
        ConditionResistanceModifier,
        ConditionTemplate,
    )
    from world.conditions.services import apply_condition  # noqa: PLC0415

    if library_template is not None:
        alteration_template = library_template
        condition_template = library_template.condition_template
    else:
        condition_template = ConditionTemplate.objects.create(
            name=name,
            category=_get_or_create_alteration_category(),
            player_description=player_description,
            observer_description=observer_description,
            default_duration_type=DurationType.PERMANENT,
        )

        if weakness_damage_type and weakness_magnitude > 0:
            ConditionResistanceModifier.objects.create(
                condition=condition_template,
                damage_type=weakness_damage_type,
                modifier_value=-weakness_magnitude,  # negative = vulnerability
            )

        # TODO: Create ConditionCheckModifier for social_reactivity when
        # observer targeting is resolved (Open Question #1 in spec).
        # Current behavior: magnitude is stored on the template but no effect
        # row is created; the value is a data-capture placeholder.

        # TODO: Create resonance bonus modifier when the target model for
        # resonance bonuses is clarified. Current behavior: magnitude is stored
        # on the template but no effect row is created.

        alteration_template = MagicalAlterationTemplate.objects.create(
            condition_template=condition_template,
            tier=pending.tier,
            origin_affinity=pending.origin_affinity,
            origin_resonance=pending.origin_resonance,
            weakness_damage_type=weakness_damage_type,
            weakness_magnitude=weakness_magnitude,
            resonance_bonus_magnitude=resonance_bonus_magnitude,
            social_reactivity_magnitude=social_reactivity_magnitude,
            is_visible_at_rest=is_visible_at_rest,
            authored_by=resolved_by,
            parent_template=parent_template,
            is_library_entry=is_library_entry,
        )

    # Apply the condition to the character (CharacterSheet.character is the ObjectDB)
    target_obj = pending.character.character
    result = apply_condition(target_obj, condition_template)

    if not result.success or result.instance is None:
        raise AlterationResolutionError

    # Create the audit event
    event = MagicalAlterationEvent.objects.create(
        character=pending.character,
        alteration_template=alteration_template,
        active_condition=result.instance,
        triggering_scene=pending.triggering_scene,
        triggering_technique=pending.triggering_technique,
        triggering_intensity=pending.triggering_intensity,
        triggering_control=pending.triggering_control,
        triggering_anima_cost=pending.triggering_anima_cost,
        triggering_anima_deficit=pending.triggering_anima_deficit,
        triggering_soulfray_stage=pending.triggering_soulfray_stage,
        audere_active=pending.audere_active,
    )

    # Mark pending as resolved
    pending.status = PendingAlterationStatus.RESOLVED
    pending.resolved_alteration = alteration_template
    pending.resolved_at = timezone.now()
    pending.resolved_by = resolved_by
    pending.save()

    return AlterationResolutionResult(
        pending=pending,
        template=alteration_template,
        condition_instance=result.instance,
        event=event,
    )


def _get_or_create_alteration_category() -> ConditionCategory:
    """Get or create the ConditionCategory for Mage Scars."""
    from world.conditions.models import ConditionCategory  # noqa: PLC0415

    cat, _ = ConditionCategory.objects.get_or_create(
        name="Magical Alteration",
        defaults={"description": "Permanent magical changes from Soulfray overburn."},
    )
    return cat


def has_pending_alterations(character: CharacterSheet) -> bool:
    """Check if this character has any unresolved Mage Scars."""
    return PendingAlteration.objects.filter(
        character=character,
        status=PendingAlterationStatus.OPEN,
    ).exists()


def staff_clear_alteration(
    *,
    pending: PendingAlteration,
    staff_account: AccountDB | None,
    notes: str = "",
) -> None:
    """Clear a PendingAlteration without resolving it. Staff escape hatch."""
    pending.status = PendingAlterationStatus.STAFF_CLEARED
    pending.resolved_by = staff_account
    pending.resolved_at = timezone.now()
    pending.notes = notes
    pending.save()
