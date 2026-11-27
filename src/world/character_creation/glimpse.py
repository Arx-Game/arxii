"""The Glimpse as a draft holds it (#5292).

A draft keeps its Glimpse answers (``draft_data["glimpse_tag_ids"]``), its story and how
much of the Glimpse the character remembers (``draft_data["glimpse_memory"]``). Answers
and story a player gave stay in the draft when they are no longer asked, so a player who
changes their mind finds them again; only the *asked* answers open offer lines and are
written to the character. This module is the one place that says which those are, read
by the offers code, the draft's validation and finalize.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.constants import (
    GLIMPSE_AXIS_CONFIG,
    GlimpseMemory,
    GlimpseTagAxis,
    glimpse_axes_asked,
)

if TYPE_CHECKING:
    from world.character_creation.models import CharacterDraft
    from world.magic.models import GlimpseTag

GLIMPSE_MEMORY_KEY = "glimpse_memory"
GLIMPSE_TAG_IDS_KEY = "glimpse_tag_ids"
GLIMPSE_STORY_KEY = "glimpse_story"


def draft_glimpse_memory(draft: CharacterDraft) -> GlimpseMemory:
    """How much of the Glimpse this draft's character remembers.

    A beginning ticked ``no_glimpse_memory`` (the Sleeper) is always no memory, whatever
    the draft holds. A draft that never chose reads as remembered.
    """
    beginning = draft.selected_beginnings
    if beginning is not None and beginning.no_glimpse_memory:
        return GlimpseMemory.NO_MEMORY
    raw = draft.draft_data.get(GLIMPSE_MEMORY_KEY)
    if raw in GlimpseMemory.values:
        return GlimpseMemory(raw)
    return GlimpseMemory.REMEMBERED


def asked_glimpse_tags(draft: CharacterDraft) -> list[GlimpseTag]:
    """The draft's Glimpse answers that count: asked in its memory state, one for each part.

    The draft's save refuses a second answer in a part that takes one, so a list with
    two can only come by another route (a GM's draft, a fixture). The first in the
    draft's own order is kept then, and nothing fails. A part set to take several
    (``GLIMPSE_AXIS_CONFIG``, none today) keeps them all.
    """
    from world.magic.models import GlimpseTag  # noqa: PLC0415

    axes = glimpse_axes_asked(draft_glimpse_memory(draft))
    tag_ids = draft.draft_data.get(GLIMPSE_TAG_IDS_KEY) or []
    if not axes or not tag_ids:
        return []
    by_id = {tag.pk: tag for tag in GlimpseTag.objects.filter(pk__in=tag_ids, is_active=True)}
    asked: list[GlimpseTag] = []
    answered: set[str] = set()
    for tag_id in tag_ids:
        tag = by_id.get(tag_id)
        if tag is None or tag.axis not in axes:
            continue
        if tag.axis in answered and not GLIMPSE_AXIS_CONFIG[GlimpseTagAxis(tag.axis)].multi:
            continue
        answered.add(tag.axis)
        asked.append(tag)
    return asked


def draft_glimpse_story(draft: CharacterDraft) -> str:
    """The story finalize writes: the draft's own, when the Glimpse is created in CG."""
    if not glimpse_axes_asked(draft_glimpse_memory(draft)):
        return ""
    return draft.draft_data.get(GLIMPSE_STORY_KEY, "")
