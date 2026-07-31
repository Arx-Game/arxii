"""Carrying an unconscious body (#2852): pick up, bring along, set down.

A character who cannot act (unconscious or dead — ``can_act`` False) can be
picked up by a co-located character and carried from room to room: the
``CarriedBody`` link is created here and the carrier's ``at_post_move`` hook
brings the body along (raw ``move_to``, the captivity/auto-flee precedent —
``move_object`` refuses third parties by design). PC bodies are gated on the
``body-handling`` consent category (a body-autonomy call, allowlist default);
NPC bodies are open. The carry releases on set-down, and automatically the
moment the carried character can act again — nobody carries the awake.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.roster.models import RosterTenure
    from world.vitals.models import CarriedBody

logger = logging.getLogger(__name__)


class CarryError(Exception):
    """Base carry failure with a player-safe message."""

    user_message = "You can't do that."

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)


def pick_up_body(carrier: ObjectDB, target: ObjectDB) -> CarriedBody:
    """Pick up *target*'s body. Raises CarryError with the reason on refusal."""
    from world.vitals.models import CarriedBody  # noqa: PLC0415
    from world.vitals.services import can_act  # noqa: PLC0415

    carrier_sheet = carrier.character_sheet
    target_sheet = target.character_sheet
    if carrier_sheet is None or target_sheet is None:
        msg = "There is nothing there to carry."
        raise CarryError(msg)
    if carrier == target:
        msg = "You cannot carry yourself."
        raise CarryError(msg)
    if carrier.location is None or carrier.location != target.location:
        msg = "They are not here."
        raise CarryError(msg)
    if can_act(target_sheet):
        msg = f"{target.key} is in no state to be slung over a shoulder — ask them."
        raise CarryError(msg)
    if not can_act(carrier_sheet):
        msg = "You are in no state to carry anyone."
        raise CarryError(msg)
    if CarriedBody.objects.filter(carrier=carrier_sheet).exists():
        msg = "Your arms are already full."
        raise CarryError(msg)
    if CarriedBody.objects.filter(carried=target_sheet).exists():
        msg = f"Someone is already carrying {target.key}."
        raise CarryError(msg)
    if _consent_blocks_body_handling(carrier_sheet, target_sheet, target):
        msg = f"{target.key}'s player has not consented to body handling."
        raise CarryError(msg)
    link = CarriedBody.objects.create(carrier=carrier_sheet, carried=target_sheet)
    carrier.msg(f"You gather up {target.key} and lift them across your shoulders.")
    if carrier.location is not None:
        carrier.location.msg_contents(
            f"{carrier.key} lifts {target.key}'s limp form.",
            exclude=[carrier],
        )
    return link


def set_down_body(carrier: ObjectDB) -> None:
    """Set down whatever body the carrier holds. Raises CarryError if none."""
    from world.vitals.models import CarriedBody  # noqa: PLC0415

    carrier_sheet = carrier.character_sheet
    link = (
        CarriedBody.objects.filter(carrier=carrier_sheet).select_related("carried").first()
        if carrier_sheet is not None
        else None
    )
    if link is None:
        msg = "You are not carrying anyone."
        raise CarryError(msg)
    carried_name = _carried_key(link)
    link.delete()
    carrier.msg(f"You ease {carried_name} down.")
    if carrier.location is not None:
        carrier.location.msg_contents(
            f"{carrier.key} eases {carried_name} down gently.",
            exclude=[carrier],
        )


def carried_body_follow(carrier: ObjectDB) -> None:
    """Bring the carried body along after the carrier moves (at_post_move hook).

    Releases the carry instead when the carried character can act again —
    nobody gets carried awake.
    """
    from world.vitals.models import CarriedBody  # noqa: PLC0415
    from world.vitals.services import can_act  # noqa: PLC0415

    carrier_sheet = carrier.character_sheet
    if carrier_sheet is None:
        return
    link = CarriedBody.objects.filter(carrier=carrier_sheet).select_related("carried").first()
    if link is None:
        return
    if can_act(link.carried):
        link.delete()
        return
    carried_obj = link.carried.character
    if carried_obj is None or carrier.location is None:
        return
    carried_obj.move_to(carrier.location, quiet=True)


def _carried_key(link: CarriedBody) -> str:
    carried_obj = link.carried.character
    return carried_obj.key if carried_obj is not None else "the body"


def _consent_blocks_body_handling(
    carrier_sheet: CharacterSheet | None,
    target_sheet: CharacterSheet,
    target: ObjectDB,
) -> bool:
    """Body-handling consent for PC targets; NPC bodies are open."""
    from world.consent.services import (  # noqa: PLC0415
        body_handling_category,
        consent_blocks_targeting,
    )

    if target.db_account is None:
        return False
    owner_tenure = _active_tenure_for_sheet(target_sheet)
    actor_tenure = _active_tenure_for_sheet(carrier_sheet)
    if owner_tenure is None:
        return False
    return consent_blocks_targeting(
        owner_tenure=owner_tenure,
        category=body_handling_category(),
        actor_tenure=actor_tenure,
    )


def _active_tenure_for_sheet(sheet: CharacterSheet | None) -> RosterTenure | None:
    """The sheet's current RosterTenure, if any (mirrors the makeover gate)."""
    from world.roster.models import RosterTenure  # noqa: PLC0415

    if sheet is None:
        return None
    return RosterTenure.objects.filter(
        roster_entry__character_sheet=sheet, end_date__isnull=True
    ).first()
