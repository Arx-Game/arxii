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

from django.utils import timezone

from world.missions.services.visibility import template_visible_to
from world.scenes.services import MissingPrimaryPersonaError, persona_for_character

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from typeclasses.characters import Character
    from world.missions.models import MissionGiver, MissionInstance, MissionTemplate

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


class BoardTakeError(Exception):
    """Typed error for a failed board take (ineligible / not on board / inactive).

    Follows the project's typed-exception convention so views and commands
    surface a safe message rather than raw ``str(exc)``.
    """

    # Class-level constants — avoid inline string literals in raise
    # statements (TRY003/EM101).
    _MSG_UNAVAILABLE = "That board is not available."
    _MSG_NOT_ON_BOARD = "That posting is not on this board."
    _MSG_INELIGIBLE = "You are not eligible for that posting."

    UNAVAILABLE: str = _MSG_UNAVAILABLE
    NOT_ON_BOARD: str = _MSG_NOT_ON_BOARD
    INELIGIBLE: str = _MSG_INELIGIBLE

    def __init__(self, user_message: str) -> None:
        self.user_message = user_message
        super().__init__(user_message)


# Default re-offer cooldown when a taken template carries no cooldown of its own.
# Mirrors trigger_dispatch._DEFAULT_COOLDOWN so the two paths stay in sync.
_DEFAULT_COOLDOWN = timezone.timedelta(hours=12)


def take_from_board(giver: MissionGiver, character: ObjectDB, template_id: int) -> MissionInstance:
    """Re-run eligibility for ``template_id`` on ``giver``, then grant.

    The preview list from :func:`postings_for_giver` is stale the instant
    it's rendered (cooldowns, level changes, …). This function re-checks:

    1. The giver is active and kind BOARD.
    2. The template is in the giver's pool (not a random pk) and active.
    3. ``template_visible_to`` still passes for this character.

    On success, grants via ``staff_assign_mission`` (the same primitive
    trigger dispatch uses) and writes a ``MissionGiverCooldown``.

    Args:
        giver: The BOARD-kind giver to take from.
        character: The character accepting the posting.
        template_id: The pk of the template to accept.

    Returns:
        The started ``MissionInstance``.

    Raises:
        BoardTakeError: Template not on this board, not eligible, giver
            inactive, or not a BOARD-kind giver.
    """
    from world.missions.constants import GiverKind  # noqa: PLC0415
    from world.missions.models import MissionGiverCooldown  # noqa: PLC0415
    from world.missions.services.run import staff_assign_mission  # noqa: PLC0415

    if not giver.is_active or giver.giver_kind != GiverKind.BOARD:
        raise BoardTakeError(BoardTakeError.UNAVAILABLE)
    template = giver.templates.filter(pk=template_id, is_active=True).first()
    if template is None:
        raise BoardTakeError(BoardTakeError.NOT_ON_BOARD)
    try:
        persona = persona_for_character(cast("Character", character))
    except MissingPrimaryPersonaError:
        persona = None
    if not template_visible_to(template, character, persona=persona):
        raise BoardTakeError(BoardTakeError.INELIGIBLE)
    instance = staff_assign_mission(template, character)
    available_at = timezone.now() + (template.cooldown or _DEFAULT_COOLDOWN)
    MissionGiverCooldown.objects.update_or_create(
        giver=giver, character=character, defaults={"available_at": available_at}
    )
    return instance


__all__ = (
    "MAX_BOARD_POSTINGS",
    "BoardPosting",
    "BoardTakeError",
    "postings_for_giver",
    "take_from_board",
)
