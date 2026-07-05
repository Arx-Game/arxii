"""Story-critical NPC protection (#1874).

Prevents external actors from killing NPCs that are load-bearing for a
player's story. The NPC flees instead of dying.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.stories.constants import BeatOutcome
from world.stories.models import StoryNPCDependency, StoryParticipation
from world.stories.types import StoryStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet


def is_death_prevented_by_story(
    npc_sheet: CharacterSheet,
    attacker: ObjectDB | None,
) -> bool:
    """Return True if the NPC's death is prevented by story-criticality.

    Checks all active ``StoryNPCDependency`` rows for the NPC. For each, verifies
    whether the attacker is a participant in that story (via
    ``StoryParticipation``). If ANY active dependency has a non-participant
    attacker, death is prevented.

    Returns False (death permitted) when:
    - No active dependencies exist for this NPC.
    - The attacker is a participant in ALL active dependent stories.
    - All dependencies are inactive (story concluded, beat resolved, or
      manually deactivated).

    Returns True (death prevented) when:
    - Any active dependency exists and the attacker is not a participant in
      that story.
    - Any active dependency exists and the attacker is None (environmental
      death — a story-critical NPC is also protected from non-actor sources).

    This is a parallel gate to ``has_death_deferred`` — both are independent
    checks in the death-gate sequence.

    Args:
        npc_sheet: The NPC's CharacterSheet.
        attacker: The attacking character's ObjectDB, or None for environmental.

    Returns:
        True if death is prevented, False if permitted.
    """
    deps = list(
        StoryNPCDependency.objects.filter(
            npc_sheet=npc_sheet,
            is_active=True,
        ).select_related("story", "beat")
    )

    if not deps:
        return False

    for dep in deps:
        if dep.beat is not None:
            if dep.beat.outcome != BeatOutcome.UNSATISFIED:
                continue
        elif dep.story.status != StoryStatus.ACTIVE:
            continue

        if attacker is None:
            return True

        is_participant = StoryParticipation.objects.filter(
            story=dep.story,
            character=attacker,
            is_active=True,
        ).exists()

        if not is_participant:
            return True

    return False
