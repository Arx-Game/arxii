"""The named NPCs a story already uses (#4373).

A GM may stand a named NPC as an opponent (a beat's opponent line, or Add Opponent on a
live encounter) only when the story already uses that NPC: its sheet is the subject of
one of the story's NPC fate stakes or protected subjects, or the NPC a beat's regard
requirement reads, or the NPC already stands on one of the story's opponent lines. The
NPC's primary persona is the one that stands. Staff may pick any persona.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from world.scenes.models import Persona
    from world.stories.models import Story


def story_npc_personas(story: Story) -> QuerySet[Persona]:
    """Every persona ``story`` may stand as a named NPC opponent, by name."""
    from world.scenes.constants import PersonaType  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.stories.constants import StakeSubjectKind  # noqa: PLC0415
    from world.stories.models import (  # noqa: PLC0415
        Beat,
        BeatOpponentLine,
        Stake,
        StoryProtectedSubject,
    )

    beats = Beat.objects.filter(episode__chapter__story=story)
    stake_sheets = Stake.objects.filter(
        beat__in=beats, subject_kind=StakeSubjectKind.NPC_FATE, subject_sheet__isnull=False
    ).values("subject_sheet_id")
    protected_sheets = StoryProtectedSubject.objects.filter(
        story=story, subject_kind=StakeSubjectKind.NPC_FATE, subject_sheet__isnull=False
    ).values("subject_sheet_id")
    regard_sheets = beats.filter(required_npc_sheet__isnull=False).values("required_npc_sheet_id")
    placed = BeatOpponentLine.objects.filter(beat__in=beats, persona__isnull=False).values(
        "persona_id"
    )
    sheets = (
        Q(character_sheet_id__in=stake_sheets)
        | Q(character_sheet_id__in=protected_sheets)
        | Q(character_sheet_id__in=regard_sheets)
    )
    return Persona.objects.filter(
        (sheets & Q(persona_type=PersonaType.PRIMARY)) | Q(pk__in=placed)
    ).order_by("name")


def may_stand_persona(story: Story | None, persona: Persona, *, is_staff: bool) -> bool:
    """Whether a GM of ``story`` (or staff) may stand ``persona`` as an opponent.

    A player character who opted in to being read and pressed (#4441) may be stood by any
    GM; the story's own cast covers every other persona.
    """
    from world.standoffs.services.character_profile import may_stand_as_opponent  # noqa: PLC0415

    if is_staff or may_stand_as_opponent(persona):
        return True
    if story is None:
        return False
    return story_npc_personas(story).filter(pk=persona.pk).exists()
