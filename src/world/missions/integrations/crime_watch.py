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

    sheet = line.deed.actor
    accepted = line.deed.instance.accepted_as_persona
    if accepted is not None and accepted.character_sheet_id == sheet.pk:
        return accepted
    return active_persona_for_sheet(sheet)


def flag_crime(line: MissionDeedRewardLine, *, room: ObjectDB) -> None:
    """Mint the criminal consequences of one CRIME_WATCH line at ``room``.

    Resolves the CrimeKind slug and the deed-time persona, then delegates the
    heat + reputation core to
    :func:`world.justice.services.report_witnessed_crime` (#2987), the same
    seam a WITNESS reaction window's "report" choice calls. An unknown
    ``ref`` slug is an authoring gap: logged loudly, never raised (the report
    must not crash on a typo).
    """
    from world.justice.models import CrimeKind  # noqa: PLC0415
    from world.justice.services import report_witnessed_crime  # noqa: PLC0415

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
    report_witnessed_crime(persona=persona, crime_kind=kind, room=room)
