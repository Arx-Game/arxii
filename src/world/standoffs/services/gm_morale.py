"""The GM morale control: move a standoff group one morale state, with a reason (#4354).

For the case where a player does something no authored row anticipated. Every active
member moves one state (steady to faltering to broken when shaken, back when steadied)
by setting its morale just past the next threshold. The reason is recorded as a
``StandoffMoraleRuling``; the room sees a plain system line. Refused on a group none of
whose members has morale (a mindless tier) and outside a standoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction

from world.combat.constants import BREAK_MORALE_THRESHOLD, FALTER_MORALE_THRESHOLD
from world.combat.morale import OpponentMoraleState, morale_state_for, tier_has_morale
from world.standoffs.constants import LIVE_GROUP_STATES, MoraleDirection
from world.standoffs.models import StandoffGroup, StandoffMoraleRuling
from world.standoffs.services.state import active_members, flush_cache_on_error, is_in_standoff

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.combat.models import CombatOpponent

_MSG_NOT_IN_STANDOFF = "That group is not in a standoff."
_MSG_NEED_REASON = "Give a reason for the ruling."
_MSG_NO_MORALE = "They have no morale to move."
_MSG_NO_CHANGE_SHAKE = "They are already broken."
_MSG_NO_CHANGE_STEADY = "They are already steady."

# Shaking moves a member down one state; steadying moves it up one. The value is the
# morale it lands on: exactly at the lower state's ceiling, or one past it going up.
_SHAKE_TO: dict[str, int] = {
    OpponentMoraleState.STEADY: FALTER_MORALE_THRESHOLD,
    OpponentMoraleState.FALTER: BREAK_MORALE_THRESHOLD,
}
_STEADY_TO: dict[str, int] = {
    OpponentMoraleState.BREAK: BREAK_MORALE_THRESHOLD + 1,
    OpponentMoraleState.FALTER: FALTER_MORALE_THRESHOLD + 1,
}
_LINE_WORD: dict[str, str] = {
    OpponentMoraleState.FALTER: "falters",
    OpponentMoraleState.BREAK: "breaks",
}


@dataclass(frozen=True)
class MoraleRulingOutcome:
    """What the control did: the room line it produced, or why it was refused."""

    success: bool
    message: str
    room_line: str = ""
    attack_line: str = ""


def _moved_morale(member: CombatOpponent, direction: str) -> int | None:
    """The morale this member moves to, or None when it cannot move that way."""
    table = _SHAKE_TO if direction == MoraleDirection.SHAKE else _STEADY_TO
    target = table.get(morale_state_for(member))
    if target is None:
        return None
    return min(target, member.max_morale) if member.max_morale else target


def _room_line(group: StandoffGroup, direction: str, members: list[CombatOpponent]) -> str:
    name = group.name
    if direction == MoraleDirection.STEADY:
        return f"{name} steadies."
    states = {morale_state_for(member) for member in members}
    worst = OpponentMoraleState.BREAK if OpponentMoraleState.BREAK in states else None
    return f"{name} {_LINE_WORD[worst or OpponentMoraleState.FALTER]}."


def shift_group_morale(
    group: StandoffGroup, direction: str, reason: str, *, ruled_by: AccountDB | None
) -> MoraleRulingOutcome:
    """Move ``group`` one morale state in ``direction``. Authorization is the caller's job."""
    reason = reason.strip()
    if not reason:
        return MoraleRulingOutcome(False, _MSG_NEED_REASON)
    if direction not in MoraleDirection.values:
        return MoraleRulingOutcome(False, "Shake or steady?")
    return _shift_locked(group, direction, reason, ruled_by=ruled_by)


@flush_cache_on_error(lambda group, *_, **__: group.encounter)
@transaction.atomic
def _shift_locked(
    group: StandoffGroup, direction: str, reason: str, *, ruled_by: AccountDB | None
) -> MoraleRulingOutcome:
    from world.combat.models import CombatEncounter  # noqa: PLC0415
    from world.standoffs.services.force import clear_override, evaluate_causes  # noqa: PLC0415

    encounter = CombatEncounter.objects.select_for_update().get(pk=group.encounter_id)
    encounter.refresh_from_db()
    group = StandoffGroup.objects.select_for_update().get(pk=group.pk)
    group.refresh_from_db()
    if not is_in_standoff(encounter) or group.state not in LIVE_GROUP_STATES:
        return MoraleRulingOutcome(False, _MSG_NOT_IN_STANDOFF)
    members = active_members(group)
    if not members or not any(tier_has_morale(member) for member in members):
        return MoraleRulingOutcome(False, _MSG_NO_MORALE)
    moved = False
    for member in members:
        target = _moved_morale(member, direction)
        if target is None or target == member.morale:
            continue
        member.morale = target
        member.save(update_fields=["morale"])
        moved = True
    if not moved:
        return MoraleRulingOutcome(
            False,
            _MSG_NO_CHANGE_SHAKE if direction == MoraleDirection.SHAKE else _MSG_NO_CHANGE_STEADY,
        )
    StandoffMoraleRuling.objects.create(
        group=group, ruled_by=ruled_by, direction=direction, reason=reason
    )
    # Morale is part of force: a standing override no longer describes this group.
    clear_override(group)
    attack_lines: list[str] = []
    evaluate_causes(encounter, attack_lines)
    line = _room_line(group, direction, members)
    return MoraleRulingOutcome(
        True,
        line,
        room_line=line,
        attack_line=attack_lines[0] if attack_lines else "",
    )
