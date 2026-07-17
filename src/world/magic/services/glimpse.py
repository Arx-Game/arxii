"""Glimpse guided-flow write services (#2427).

Single write path for a character's Glimpse: tag picks per axis, the prose
story, and distinction provenance links. Every mutation recomputes
``CharacterAura.glimpse_state`` so the cached state never drifts from the
prose + tag rows (the field is a cache of truth, mirroring the ``is_secret``
FK-presence precedent).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

from world.magic.constants import GLIMPSE_AXIS_CONFIG, GlimpseState, GlimpseTagAxis
from world.magic.models.glimpse import CharacterGlimpseTag

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.distinctions.models import CharacterDistinction
    from world.magic.models.aura import CharacterAura
    from world.magic.models.glimpse import GlimpseTag


def refresh_glimpse_state(aura: CharacterAura) -> GlimpseState:
    """Recompute and persist ``glimpse_state`` from prose + tag rows."""
    if aura.glimpse_story.strip():
        state = GlimpseState.COMPLETE
    elif CharacterGlimpseTag.objects.filter(aura=aura).exists():
        state = GlimpseState.TAGS_ONLY
    else:
        state = GlimpseState.NOT_STARTED
    if aura.glimpse_state != state:
        aura.glimpse_state = state
        aura.save()
    return state


@transaction.atomic
def set_glimpse_tags(
    aura: CharacterAura, tags: Sequence[GlimpseTag], *, axis: GlimpseTagAxis
) -> None:
    """Replace the character's chosen tags for one axis.

    Enforces the axis's select-arity (``GLIMPSE_AXIS_CONFIG``) and that every
    tag belongs to ``axis``. An empty ``tags`` clears the axis.
    """
    rule = GLIMPSE_AXIS_CONFIG[GlimpseTagAxis(axis)]
    if not rule.multi and len(tags) > 1:
        msg = f"{GlimpseTagAxis(axis).label} accepts a single tag."
        raise ValidationError(msg)
    wrong = [tag.name for tag in tags if tag.axis != axis]
    if wrong:
        msg = f"Tags not on the {GlimpseTagAxis(axis).label} axis: {', '.join(wrong)}."
        raise ValidationError(msg)

    CharacterGlimpseTag.objects.filter(aura=aura, tag__axis=axis).delete()
    CharacterGlimpseTag.objects.bulk_create(CharacterGlimpseTag(aura=aura, tag=tag) for tag in tags)
    refresh_glimpse_state(aura)


def set_glimpse_prose(aura: CharacterAura, text: str) -> None:
    """Write the glimpse story prose and recompute the state."""
    aura.glimpse_story = text
    aura.save()
    refresh_glimpse_state(aura)


def link_distinction_to_glimpse(
    character_distinction: CharacterDistinction, aura: CharacterAura
) -> None:
    """Mark a distinction as born in this character's Glimpse."""
    if character_distinction.character_id != aura.character_id:
        msg = "Distinction and aura belong to different characters."
        raise ValidationError(msg)
    character_distinction.from_glimpse = aura
    character_distinction.save()


def unlink_distinction_from_glimpse(character_distinction: CharacterDistinction) -> None:
    """Clear a distinction's Glimpse provenance."""
    character_distinction.from_glimpse = None
    character_distinction.save()
