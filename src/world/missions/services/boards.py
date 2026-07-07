"""Notice-board postings — preview-only eligibility filter (#2044).

A BOARD-kind :class:`~world.missions.models.MissionGiver` lists many
eligible postings when examined, unlike ENVIRONMENTAL_DETAIL which
auto-grants one drawn template. This module provides the preview list
(eligibility filter WITHOUT grant / cooldown / announce side effects)
and the ``take_from_board`` grant step that re-runs eligibility before
granting through the same ``staff_assign_mission`` path trigger dispatch
uses.

Both paths route through :func:`template_visible_to` — there is no
second eligibility predicate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from world.missions.services.visibility import template_visible_to
from world.scenes.services import MissingPrimaryPersonaError, persona_for_character

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from typeclasses.characters import Character
    from world.missions.models import MissionGiver, MissionTemplate

#: Cap on how many postings a board preview renders (constant; #2044).
MAX_BOARD_POSTINGS = 10


@dataclass(frozen=True, slots=True)
class BoardPosting:
    """One eligible posting on a board, for preview rendering.

    Carries just enough for the examine / API / telnet surfaces to render
    a row: the template pk (for the take step), display name, and summary.
    """

    template_id: int
    name: str
    summary: str
    giver_name: str


def postings_for_giver(giver: MissionGiver, character: ObjectDB) -> list[BoardPosting]:
    """Return the character's eligible postings on ``giver``, without granting.

    Filters the giver's ``templates`` pool through
    :func:`template_visible_to` — the SAME gate trigger dispatch and the
    NPC-offer path use. No cooldown check, no grant, no announce: this is
    pure preview. Capped at :data:`MAX_BOARD_POSTINGS`.

    Returns an empty list when the character has no eligible templates
    (RESTRICTED + failing predicate, or all inactive).
    """
    try:
        persona = persona_for_character(cast("Character", character))
    except MissingPrimaryPersonaError:
        persona = None

    eligible: list[MissionTemplate] = []
    for template in giver.templates.all():
        if template.is_active and template_visible_to(template, character, persona=persona):
            eligible.append(template)
        if len(eligible) >= MAX_BOARD_POSTINGS:
            break
    return [
        BoardPosting(
            template_id=t.pk,
            name=t.name,
            summary=t.summary or "",
            giver_name=giver.name,
        )
        for t in eligible
    ]


__all__ = (
    "MAX_BOARD_POSTINGS",
    "BoardPosting",
    "postings_for_giver",
)
