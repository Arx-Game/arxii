"""Crime-watch propagation — the criminal-consequence writer (#1765).

Replaces the Phase-5b.1 raise-stub. A ``PROPAGATION/CRIME_WATCH`` reward line
is the mission author's declaration "this deed is a watched crime"; ``ref``
carries the :class:`world.justice.models.CrimeKind` slug. At report time the
line mints pursuit heat against the *deed-time* persona (the mask the actor
ran the mission as, when recorded) at the report location, and stings the
enforcing society's regard for that persona.

Mission-born legend entries are deliberately NOT crime-tagged here yet — the
entry↔deed-record mapping is ambiguous for multi-actor runs, so tellings of a
mission deed spread cold for now (flagged on #1765; scene-born deeds get the
knowledge-seam writer).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from evennia.utils import logger

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.missions.models import MissionDeedRewardLine
    from world.scenes.models import Persona


def _deed_time_persona(line: MissionDeedRewardLine) -> Persona | None:
    """The persona the actor presented on this run — the face that soaks the heat.

    Prefers ``MissionInstance.accepted_as_persona`` (the mask the contract
    holder presented at acceptance, #686) when it belongs to the actor; falls
    back to the actor's currently-active persona for other participants and
    trigger-based/legacy rows that never recorded one.
    """
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    actor = line.deed.actor
    sheet = actor.character_sheet
    accepted = line.deed.instance.accepted_as_persona
    if accepted is not None and sheet is not None and accepted.character_sheet_id == sheet.pk:
        return accepted
    return active_persona_for_sheet(sheet) if sheet is not None else None


def flag_crime(line: MissionDeedRewardLine, *, room: ObjectDB) -> None:
    """Mint the criminal consequences of one CRIME_WATCH line at ``room``.

    Heat: :func:`world.justice.services.accrue_heat` against the deed-time
    persona, judged by the law cascade at the report location (no law / out of
    jurisdiction → silently nothing — legal there). Reputation: the enforcing
    society's regard drops by the winning law's weight (established/primary
    personas only). An unknown ``ref`` slug is an authoring gap — logged
    loudly, never raised (the report must not crash on a typo).
    """
    from world.justice.models import CrimeKind  # noqa: PLC0415
    from world.justice.services import (  # noqa: PLC0415
        accrue_heat,
        area_for_room,
        enforcing_society_for,
        law_for,
    )
    from world.societies.renown import bump_society_reputation  # noqa: PLC0415

    kind = CrimeKind.objects.filter(slug=line.ref).first()
    if kind is None:
        logger.log_warn(
            f"crime_watch.flag_crime: line pk={line.pk} ref={line.ref!r} matches no "
            "CrimeKind slug — authoring gap, consequence dropped (#1765)."
        )
        return
    persona = _deed_time_persona(line)
    if persona is None:
        logger.log_warn(
            f"crime_watch.flag_crime: line pk={line.pk} has no resolvable persona — skipped."
        )
        return
    area = area_for_room(room)
    row = accrue_heat(persona=persona, crime_kind=kind, area=area, scale=1)
    if row is None:
        return  # legal here / out of jurisdiction — no consequence.
    law = law_for(area, kind)
    society = enforcing_society_for(law.area) if law is not None else None
    if society is not None:
        # PLACEHOLDER magnitude: the reputation sting mirrors the heat weight.
        bump_society_reputation(persona, society, -law.heat_weight)
