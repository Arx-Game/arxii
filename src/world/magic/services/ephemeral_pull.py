"""Service for applying non-combat CAPABILITY_GRANT pulls via the condition system (#2840).

When a non-combat thread pull resolves a CAPABILITY_GRANT effect, the frozen
curved value is persisted as a Thread Surge condition + EphemeralPullCapabilityGrant
sidecar rows, so the capability oracle can read them at arbitrary later times.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.conditions.services import apply_condition
from world.magic.constants import EffectKind
from world.magic.factories import ensure_thread_surge_content
from world.magic.models import EphemeralPullCapabilityGrant

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.conditions.models import ConditionInstance
    from world.magic.types.pull import ResolvedPullEffect


def apply_ephemeral_pull_capability_grants(
    character_sheet: CharacterSheet,
    resolved: list[ResolvedPullEffect],
) -> ConditionInstance | None:
    """Apply a Thread Surge condition + sidecar rows for non-combat CAPABILITY_GRANT effects.

    Called from ``spend_resonance_for_pull`` after the debit, when not in combat
    and the resolved effects contain at least one CAPABILITY_GRANT.

    1. Get the "Thread Surge" ConditionTemplate via ``ensure_thread_surge_content``.
    2. Apply the condition (SCENE duration, non-stackable — the condition system
       returns the same instance for a second pull in the same scene).
    3. For each CAPABILITY_GRANT effect, upsert an EphemeralPullCapabilityGrant
       sidecar row with MAX semantics (ADR-0034).

    Returns the ConditionInstance, or None when the template isn't available
    (content repo doesn't author it and SEED_SAMPLE_CONTENT is off) or when
    there are no CAPABILITY_GRANT effects to persist.
    """
    cap_effects = [
        eff
        for eff in resolved
        if eff.kind == EffectKind.CAPABILITY_GRANT
        and eff.granted_capability is not None
        and eff.capability_grant_value is not None
        and eff.capability_grant_value > 0
    ]
    if not cap_effects:
        return None

    template = ensure_thread_surge_content()
    if template is None:
        return None

    character = character_sheet.character
    result = apply_condition(
        character,
        template,
        source_character=character,
        source_description="Thread pull capability surge",
    )
    if not result.success or result.instance is None:
        return None

    instance = result.instance
    for eff in cap_effects:
        # Upsert with MAX: if a sidecar already exists for this
        # (condition_instance, capability), keep the larger grant_value.
        existing = EphemeralPullCapabilityGrant.objects.filter(
            condition_instance=instance,
            capability=eff.granted_capability,
        ).first()
        if existing is not None:
            existing.grant_value = max(existing.grant_value, eff.capability_grant_value)
            existing.source_thread = eff.source_thread
            existing.source_thread_level = eff.source_thread_level
            existing.source_tier = eff.source_tier
            existing.save(
                update_fields=[
                    "grant_value",
                    "source_thread",
                    "source_thread_level",
                    "source_tier",
                ]
            )
        else:
            EphemeralPullCapabilityGrant.objects.create(
                condition_instance=instance,
                character_sheet=character_sheet,
                capability=eff.granted_capability,
                grant_value=eff.capability_grant_value,
                source_thread=eff.source_thread,
                source_thread_level=eff.source_thread_level,
                source_tier=eff.source_tier,
            )
    return instance
