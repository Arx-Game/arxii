"""Narration for sustained telegraphs, erosion and breaks."""

from __future__ import annotations

from world.combat import services as _svc
from world.combat.constants import SUSTAINED_GENERIC_TELEGRAPH
from world.combat.models import SustainedAction


def _broadcast_sustained_telegraph(sustained: SustainedAction) -> None:
    """Announce a newly-declared PC sustained action (#2705).

    Always ``SUSTAINED_GENERIC_TELEGRAPH`` — unlike the NPC wind-up side,
    neither ``Technique`` nor ``Ritual`` authors a per-subject telegraph line
    (there is no analogous field), so there is nothing to fall back FROM.
    """
    character_name = str(sustained.participant.character_sheet.character)
    narration = SUSTAINED_GENERIC_TELEGRAPH.format(
        character=character_name, subject=sustained.subject_name
    )
    _svc._broadcast_commitment_line(sustained.encounter, narration)  # noqa: SLF001 (test patch seam)


def _broadcast_sustained_erosion(sustained: SustainedAction) -> None:
    """Announce a landing hit chipping away at a PC's sustained action (#2705).

    The PC-side sibling of ``_broadcast_windup_wreck``. No called-out variant:
    a PC wind-up is public by construction (it is announced the round it is
    declared, via ``_broadcast_sustained_telegraph``), never a designed reveal
    the way an unflagged NPC wind-up is — so there is only ever one erosion
    line, not a blind/called-out pair.
    """
    character_name = str(sustained.participant.character_sheet.character)
    narration = f"{character_name}'s hold on {sustained.subject_name} takes a blow!"
    _svc._broadcast_commitment_line(sustained.encounter, narration)  # noqa: SLF001 (test patch seam)


def _broadcast_sustained_broken(sustained: SustainedAction, *, reason: str = "") -> None:
    """Announce a PC sustained action breaking before it matures (#2705).

    The PC-side sibling of ``_broadcast_windup_fizzled``. Fires when
    ``downgrades >= absorption_budget`` at maturation, or when the
    participant can no longer hold the commitment together (left/died).
    """
    character_name = str(sustained.participant.character_sheet.character)
    if reason:
        narration = f"{character_name}'s hold on {sustained.subject_name} {reason}!"
    else:
        narration = f"{character_name}'s hold on {sustained.subject_name} breaks entirely!"
    _svc._broadcast_commitment_line(sustained.encounter, narration)  # noqa: SLF001 (test patch seam)


def _broadcast_sustained_held(sustained: SustainedAction) -> None:
    """Announce a PC sustained action holding through to maturation (#2705).

    No NPC-side analogue — a wind-up that matures resolves as an attack, which
    narrates through the normal NPC-attack broadcast path, not a dedicated
    "held" line. A held sustained action has no such downstream narration of
    its own (the cloned technique/dispatched ritual resolves silently into the
    normal PC pipeline), so this line is the only announcement it gets.
    """
    character_name = str(sustained.participant.character_sheet.character)
    narration = f"{character_name} completes {sustained.subject_name}!"
    _svc._broadcast_commitment_line(sustained.encounter, narration)  # noqa: SLF001 (test patch seam)
