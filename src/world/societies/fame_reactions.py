"""#881 — room-entry fame reactions: the world noticing notable arrivals.

When a character enters a room with authored :class:`FameReactionLine`
rows, the room may react: bystanders receive the observer line; the
arriver receives their own register (the actor/audience split, RENOWN
narrative category — the same delivery machinery as mission beats).

Authoring is per-room, per-society, and entirely optional — unauthored
rooms say nothing, ineligible arrivals say nothing, and any hiccup is
swallowed (an optional flavor hook must never break movement, mirroring
the #729 trigger-dispatch posture).

A society-voiced line perceives the arriver's fame tier through that
society's ``fame_perception_offset`` (the same lens as the renown tab and
the #761 boards); ``society=null`` lines read the raw tier. A
per-(persona, room) cooldown throttles re-fires so pacing the room
doesn't spam its occupants.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

from world.societies.constants import FAME_TIER_ORDER
from world.societies.models import FameReactionCooldown, FameReactionLine

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Persona

# Re-fire window per (persona, room). A future authoring knob can move
# this onto SpreadingConfig; constant for now.
_REACTION_COOLDOWN = timezone.timedelta(hours=6)


def maybe_emit_fame_reaction(character: ObjectDB, room: ObjectDB) -> bool:
    """Fire at most one authored fame reaction for ``character`` entering ``room``.

    Returns True when a reaction fired (for tests); False on any quiet
    exit (no profile, no persona, no eligible line, cooldown active).
    """
    if character is None or room is None:
        return False
    try:
        profile = room.room_profile
    except Exception:  # noqa: BLE001 — non-room containers have no profile
        return False

    persona = _presented_persona(character)
    if persona is None:
        return False

    lines = list(
        FameReactionLine.objects.filter(room=profile, is_active=True).select_related("society")
    )
    eligible = [line for line in lines if _tier_meets(persona.fame_tier, line)]
    if not eligible:
        return False

    now = timezone.now()
    if FameReactionCooldown.objects.filter(
        persona=persona, room=profile, available_at__gt=now
    ).exists():
        return False

    from world.checks.outcome_utils import select_weighted  # noqa: PLC0415

    line = select_weighted(eligible)
    _deliver(line, character, room)
    FameReactionCooldown.objects.update_or_create(
        persona=persona,
        room=profile,
        defaults={"available_at": now + _REACTION_COOLDOWN},
    )
    return True


def _presented_persona(character: ObjectDB) -> Persona | None:
    """The arriver's presented persona — PRIMARY per the #885 convention.

    Defensive: a sheet-less character (or missing PRIMARY) resolves to
    None and the reaction stays silent rather than breaking movement.
    """
    from world.scenes.services import (  # noqa: PLC0415
        MissingPrimaryPersonaError,
        persona_for_character,
    )

    try:
        return persona_for_character(character)
    except MissingPrimaryPersonaError:
        return None


def _tier_meets(fame_tier: str, line: FameReactionLine) -> bool:
    """True when the arriver's PERCEIVED tier reaches the line's threshold.

    A society-voiced line applies its society's ``fame_perception_offset``
    (insular rooms hear less); a society-less line reads the raw tier.
    """
    offset = (line.society.fame_perception_offset or 0) if line.society_id else 0
    perceived_index = max(0, FAME_TIER_ORDER.index(fame_tier) + offset)
    return perceived_index >= FAME_TIER_ORDER.index(line.min_fame_tier)


def _deliver(line: FameReactionLine, character: ObjectDB, room: ObjectDB) -> None:
    """Send the bystander line to the room (minus arriver) + the arriver line."""
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    if line.bystander_body:
        bystander_sheets = []
        for obj in room.contents:
            if obj.pk == character.pk:
                continue
            sheet = getattr(obj, "sheet_data", None)  # noqa: GETATTR_LITERAL
            if sheet is not None:
                bystander_sheets.append(sheet)
        if bystander_sheets:
            send_narrative_message(
                recipients=bystander_sheets,
                body=line.bystander_body,
                category=NarrativeCategory.RENOWN,
                ooc_note="Fame reaction (bystander register, #881).",
            )
    if line.arriver_body:
        arriver_sheet = getattr(character, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if arriver_sheet is not None:
            send_narrative_message(
                recipients=[arriver_sheet],
                body=line.arriver_body,
                category=NarrativeCategory.RENOWN,
                ooc_note="Fame reaction (arriver register, #881).",
            )
