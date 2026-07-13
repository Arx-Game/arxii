"""Dynamic thumbnail resolution for characters (#2196).

Derives the thumbnail URL from current character state on every read,
following ADR-0014 (no persisted derived data — derive on read).
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import PlayerMedia
    from world.conditions.models import ConditionInstance
    from world.scenes.models import Persona


def resolve_thumbnail(
    obj: "ObjectDB",
    *,
    persona: "Persona | None" = None,
    viewer_can_see_hidden: bool = False,
    fallback_media: "PlayerMedia | None" = None,
    cached_conditions: "list[ConditionInstance] | None" = None,
) -> str | None:
    """Resolve the thumbnail URL for an object, reflecting current state.

    Priority (first non-null wins):
    1. Active condition's stage thumbnail (highest display_priority visible condition)
    2. Active condition's template thumbnail
    3. Active alternate self's thumbnail
    4. Persona's PlayerMedia thumbnail FK
    5. ObjectDisplayData.thumbnail fallback
    6. ``fallback_media`` (e.g. CombatOpponent.portrait for persona-less NPCs)

    Args:
        obj: The ObjectDB to resolve a thumbnail for.
        persona: The active persona (if character). When None, skips
            persona-level lookups (conditions/alternate self) and falls to
            ObjectDisplayData.
        viewer_can_see_hidden: Whether the viewer can see hidden conditions.
            When False, only is_visible_to_others conditions contribute
            overrides.
        fallback_media: A PlayerMedia to use after all other levels are
            exhausted. Defaults to None.
        cached_conditions: Prefetched active conditions (avoids N+1 in list
            contexts). When None, queries ``get_active_conditions(obj)``.

    Returns:
        Cloudinary URL string, or None when no thumbnail is set at any level.
    """
    # 1-2. Condition override (stage > template, highest display_priority wins)
    condition_url = _resolve_condition_thumbnail(
        obj,
        viewer_can_see_hidden=viewer_can_see_hidden,
        cached_conditions=cached_conditions,
    )
    if condition_url is not None:
        return condition_url

    # 3. Alternate self override
    if persona is not None:
        alt_self_url = _resolve_alternate_self_thumbnail(persona)
        if alt_self_url is not None:
            return alt_self_url

        # 4. Persona default
        if persona.thumbnail_id is not None:
            return persona.thumbnail.cloudinary_url

    # 5. ObjectDisplayData fallback
    display_url = _resolve_display_data_thumbnail(obj)
    if display_url is not None:
        return display_url

    # 6. Fallback media (e.g. CombatOpponent.portrait)
    if fallback_media is not None:
        return fallback_media.cloudinary_url

    return None


def _resolve_condition_thumbnail(
    obj: "ObjectDB",
    *,
    viewer_can_see_hidden: bool,
    cached_conditions: "list[ConditionInstance] | None",
) -> str | None:
    """Check active conditions for a thumbnail override.

    Returns the first non-null thumbnail from the highest-display_priority
    visible condition. Stage thumbnail overrides template thumbnail.
    """
    if cached_conditions is not None:
        instances = cached_conditions
    else:
        from evennia.objects.models import ObjectDB  # noqa: PLC0415

        # Only ObjectDB instances can have ConditionInstance rows (the target
        # FK is to ObjectDB). Non-ObjectDB objects (e.g. ItemInstance) skip
        # condition overrides entirely.
        if not isinstance(obj, ObjectDB):
            return None
        from world.conditions.services import get_active_conditions  # noqa: PLC0415

        instances = list(get_active_conditions(obj))

    # Filter by visibility and sort by display_priority (highest first)
    visible = [
        inst for inst in instances if viewer_can_see_hidden or inst.condition.is_visible_to_others
    ]
    visible.sort(
        key=lambda inst: inst.condition.display_priority,
        reverse=True,
    )

    for inst in visible:
        # Stage thumbnail overrides template thumbnail
        if inst.current_stage_id is not None and inst.current_stage is not None:
            if inst.current_stage.thumbnail_id is not None:
                return inst.current_stage.thumbnail.cloudinary_url
        if inst.condition.thumbnail_id is not None:
            return inst.condition.thumbnail.cloudinary_url

    return None


def _resolve_alternate_self_thumbnail(persona: "Persona") -> str | None:
    """Check if the persona's character has an active alternate self with a thumbnail."""
    try:
        sheet = persona.character_sheet
    except AttributeError:
        return None
    if sheet is None:
        return None
    try:
        active = sheet.active_alternate_self
    except AttributeError:
        return None
    if active is None or active.alternate_self_id is None:
        return None
    alt_self = active.alternate_self
    if alt_self is None or alt_self.thumbnail_id is None:
        return None
    return alt_self.thumbnail.cloudinary_url


def _resolve_display_data_thumbnail(obj: "ObjectDB") -> str | None:
    """Fall back to ObjectDisplayData.thumbnail."""
    try:
        display_data = obj.display_data
    except AttributeError:
        return None
    if display_data is None or display_data.thumbnail_id is None:
        return None
    return display_data.thumbnail.cloudinary_url
