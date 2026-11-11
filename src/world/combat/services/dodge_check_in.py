"""The Soulfray check-in for automatic dodges (#5066 decision 13).

Each automatic dodge with a technique is a cast of it, so once she is in Soulfray every dodge
deepens it. Her turn asks her, as a cast does: keep dodging into Soulfray, or stop. Her answer
is ``CombatParticipant.dodge_into_soulfray``, which ``make_dodge`` hands to the cast as its
Soulfray consent.

The web client shows it from the participant payload (``dodge_check_in``, beside her dodge
plan) through the combat Soulfray gate; telnet gets a line at the start of each declaring
round and answers with ``accept dodgesoulfray`` / ``decline dodgesoulfray`` (the offer
registry, as ``accept soulfray`` answers a cast).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter, CombatParticipant
    from world.magic.types import SoulfrayWarning

CHECK_IN_LINE = (
    "You are in Soulfray ({stage}). Each automatic dodge with your technique casts it and "
    "deepens it. Type |waccept dodgesoulfray|n to keep dodging, |wdecline dodgesoulfray|n "
    "to stop."
)
KEEP_LINE = "You'll keep dodging into Soulfray."
STOP_LINE = "You won't dodge when it would cost you Soulfray."


def soulfray_check_in(participant: CombatParticipant) -> SoulfrayWarning | None:
    """Her Soulfray stage warning when her dodges would cast into it, else None.

    Asked only while she is in Soulfray and something of hers dodges with a technique.
    """
    from world.combat.services.reactions import dodge_sources  # noqa: PLC0415
    from world.magic.services.soulfray import get_soulfray_warning  # noqa: PLC0415

    warning = get_soulfray_warning(participant.character_sheet.character)
    if warning is None:
        return None
    if not any(source.technique_id is not None for source in dodge_sources(participant)):
        return None
    return warning


def announce_soulfray_check_ins(encounter: CombatEncounter) -> None:
    """Tell each player whose dodges would cast into Soulfray, as her turn opens."""
    from django.db import transaction  # noqa: PLC0415

    from world.combat.constants import ParticipantStatus  # noqa: PLC0415
    from world.combat.models import CombatParticipant  # noqa: PLC0415

    participants = CombatParticipant.objects.filter(
        encounter=encounter, status=ParticipantStatus.ACTIVE
    ).select_related("character_sheet__character")
    for participant in participants:
        warning = soulfray_check_in(participant)
        if warning is None:
            continue
        character = participant.character_sheet.character
        line = CHECK_IN_LINE.format(stage=warning.stage_name)
        transaction.on_commit(lambda c=character, msg=line: c.msg(msg))


def _declaring_participant(sheet: CharacterSheet) -> CombatParticipant | None:
    from world.combat.constants import ParticipantStatus  # noqa: PLC0415
    from world.combat.models import CombatParticipant  # noqa: PLC0415
    from world.scenes.constants import RoundStatus  # noqa: PLC0415

    return (
        CombatParticipant.objects.filter(
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
            encounter__status=RoundStatus.DECLARING,
        )
        .select_related("encounter", "character_sheet__character")
        .order_by("-encounter__created_at")
        .first()
    )


class DodgeSoulfrayHandler:
    """``accept dodgesoulfray`` keeps her dodges casting into Soulfray; ``decline`` stops them."""

    keyword = "dodgesoulfray"
    label = "Dodging into Soulfray"

    def pending_for(self, sheet: CharacterSheet) -> SoulfrayWarning | None:
        participant = _declaring_participant(sheet)
        return soulfray_check_in(participant) if participant is not None else None

    def describe(self, offer: SoulfrayWarning) -> str:
        return CHECK_IN_LINE.format(stage=offer.stage_name)

    def accept(self, offer: SoulfrayWarning, caller: ObjectDB, args: str) -> str:  # noqa: ARG002
        return _answer(caller, keep=True)

    def decline(self, offer: SoulfrayWarning, caller: ObjectDB) -> str:  # noqa: ARG002
        return _answer(caller, keep=False)


def _answer(caller: ObjectDB, *, keep: bool) -> str:  # noqa: OBJECTDB_PARAM - the answering character
    """Write her answer through the dodge settings action, the web's own path."""
    from actions.constants import ActionBackend  # noqa: PLC0415
    from actions.definitions.dodge_settings import INTO_SOULFRAY_KWARG  # noqa: PLC0415
    from actions.player_interface import dispatch_player_action  # noqa: PLC0415
    from actions.types import ActionRef  # noqa: PLC0415

    ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key="dodge_settings")
    result = dispatch_player_action(caller, ref, {INTO_SOULFRAY_KWARG: keep})
    if result.detail is not None and result.detail.message:
        return result.detail.message
    return KEEP_LINE if keep else STOP_LINE
