"""Dynamic thumbnail resolution for characters (#2196).

Derives the thumbnail URL from current character state on every read,
following ADR-0014 (no persisted derived data — derive on read).
"""

from typing import TYPE_CHECKING
from urllib.parse import quote

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import Media
    from world.conditions.models import ConditionInstance
    from world.forms.models import AlternateSelf
    from world.scenes.models import Persona

# The picture a face with no portrait shows until staff choose one in the admin (#4889): a
# plain grey head and shoulders, the same for every face. It is a data URI so it needs no
# file served beside the page and no per-face lookup; it never carries a letter or a name.
BUILTIN_FACE_PLACEHOLDER_URL = "data:image/svg+xml," + quote(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<rect width="100" height="100" fill="#d4d4d8"/>'
    '<circle cx="50" cy="38" r="18" fill="#a1a1aa"/>'
    '<path d="M14 100c0-24 16-38 36-38s36 14 36 38z" fill="#a1a1aa"/>'
    "</svg>"
)


def resolve_thumbnail(
    obj: "ObjectDB",
    *,
    persona: "Persona | None" = None,
    viewer_can_see_hidden: bool = False,
    fallback_media: "Media | None" = None,
    cached_conditions: "list[ConditionInstance] | None" = None,
) -> str | None:
    """Resolve the thumbnail URL for an object, reflecting current state.

    Priority (first non-null wins):
    1. Active condition's stage thumbnail (highest display_priority visible condition)
    2. Active condition's template thumbnail
    3. Active alternate self's thumbnail
    4. Persona's Media thumbnail FK
    5. ObjectDisplayData.thumbnail fallback, skipped when ``persona`` is a face other
       than the PRIMARY one or an alternate self is worn: the object's own image is the
       true face a mask hides (#4802, #4889)
    6. ``fallback_media`` (e.g. CombatOpponent.portrait for persona-less NPCs)
    7. The placeholder portrait, for a face that hides the real face and found no image
       above (#4889): never the real face, never nothing

    Args:
        obj: The ObjectDB to resolve a thumbnail for.
        persona: The active persona (if character). When None, skips
            persona-level lookups (conditions/alternate self) and falls to
            ObjectDisplayData.
        viewer_can_see_hidden: Whether the viewer can see hidden conditions.
            When False, only is_visible_to_others conditions contribute
            overrides.
        fallback_media: A Media to use after all other levels are
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

        # 4. Persona default. A PRIMARY face's own picture is the real one (a story NPC's
        # worn look is copied onto it), so it is skipped while an alternate self is worn.
        if persona.thumbnail_id is not None and not _worn_self_hides_primary(persona):
            return persona.thumbnail.cloudinary_url

    # 5. ObjectDisplayData fallback
    hides_true_face = persona is not None and _face_hides_true_face(persona)
    display_url = None if hides_true_face else _resolve_display_data_thumbnail(obj)
    if display_url is not None:
        return display_url

    # 6. Fallback media (e.g. CombatOpponent.portrait)
    if fallback_media is not None:
        return fallback_media.cloudinary_url

    # 7. A face that hides the real one shows the placeholder, never the real face.
    if hides_true_face:
        return placeholder_portrait_url()

    return None


def placeholder_portrait_url() -> str:
    """The one picture a face with no portrait shows (#4889).

    Staff's chosen ``FacePlaceholderConfig.placeholder`` while it exists, else the built-in
    grey silhouette, so a face with no portrait never shows a letter, the real face or a
    broken image.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from evennia_extensions.models import Media  # noqa: PLC0415
    from world.scenes.models import get_face_placeholder_config  # noqa: PLC0415

    media_id = get_face_placeholder_config().placeholder_id
    if media_id is None:
        return BUILTIN_FACE_PLACEHOLDER_URL
    try:
        media = Media.objects.get(pk=media_id)
    except ObjectDoesNotExist:
        return BUILTIN_FACE_PLACEHOLDER_URL
    # Only staff-authored art can be the placeholder; a player's private picture never is,
    # whatever wrote the link.
    return media.cloudinary_url if media.player_data_id is None else BUILTIN_FACE_PLACEHOLDER_URL


def persona_face_url(persona: "Persona") -> str:
    """The portrait URL a pose, combat or battle row shows for ``persona`` (#4889).

    The persona's own picture (the text copy a writer sets beside the Media link), else its
    Media link, else, for a face that is not the PRIMARY one, the placeholder. An empty
    string for a PRIMARY face with no picture, which the client draws as the letter avatar.
    One answer for every list that reads a persona's portrait from its text copy, so none of
    them can fall back to something else.

    A PRIMARY face that is presented while the character wears an alternate self shows that
    self's picture, or the placeholder: never the real face (a story NPC's worn look is
    copied onto the face's own text copy, a player character's look is its gallery's). Only
    a presented PRIMARY face asks which self is worn, so a list of masks costs no query per
    row; a writer of a self's picture sets its persona's copy too.
    """
    from world.scenes.constants import PersonaType  # noqa: PLC0415

    if persona.persona_type == PersonaType.PRIMARY:
        alt_self = _active_alternate_self(persona) if _is_presented(persona) else None
        if alt_self is not None:
            if alt_self.thumbnail_id is not None:
                return alt_self.thumbnail.cloudinary_url
            return placeholder_portrait_url()
    if persona.thumbnail_url:
        return persona.thumbnail_url
    if persona.thumbnail_id is not None:
        return persona.thumbnail.cloudinary_url
    if persona.persona_type != PersonaType.PRIMARY:
        return placeholder_portrait_url()
    return ""


def _active_alternate_self(persona: "Persona") -> "AlternateSelf | None":
    """The alternate self the persona's character is wearing now, or None."""
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
    return active.alternate_self


def _worn_self_hides_primary(persona: "Persona") -> bool:
    """Whether ``persona`` is the PRIMARY face and an alternate self is worn over it."""
    from world.scenes.constants import PersonaType  # noqa: PLC0415

    return (
        persona.persona_type == PersonaType.PRIMARY and _active_alternate_self(persona) is not None
    )


def _is_presented(persona: "Persona") -> bool:
    """Whether ``persona`` is the face its character presents right now."""
    from world.scenes.constants import PersonaType  # noqa: PLC0415

    sheet = persona.character_sheet
    if sheet.active_persona_id is not None:
        return sheet.active_persona_id == persona.pk
    return persona.persona_type == PersonaType.PRIMARY


def _face_hides_true_face(persona: "Persona") -> bool:
    """Whether the real face must not show for ``persona``: a mask, or a worn alternate self."""
    from world.scenes.constants import PersonaType  # noqa: PLC0415

    return (
        persona.persona_type != PersonaType.PRIMARY or _active_alternate_self(persona) is not None
    )


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
        if (
            inst.current_stage_id is not None
            and inst.current_stage is not None
            and inst.current_stage.thumbnail_id is not None
        ):
            return inst.current_stage.thumbnail.cloudinary_url
        if inst.condition.thumbnail_id is not None:
            return inst.condition.thumbnail.cloudinary_url

    return None


def _resolve_alternate_self_thumbnail(persona: "Persona") -> str | None:
    """Check if the persona's character has an active alternate self with a thumbnail."""
    alt_self = _active_alternate_self(persona)
    # Only on the face presented now: a hidden mask of the same character must not read the
    # same picture as the face on show, or the identical URL would link the two (#4889).
    if alt_self is None or alt_self.thumbnail_id is None or not _is_presented(persona):
        return None
    # A self tied to another mask keeps its picture off this one (#4889).
    if alt_self.persona_id is not None and alt_self.persona_id != persona.pk:
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
