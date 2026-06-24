"""Combat maneuver actions on the shared dispatch seam (#1453, #1452).

Each verb a player can take in a fight that is not a technique cast or a clash
commit — flee, cover, interpose, ready, join/leave the encounter, and the combo
upgrade/revert — is a real ``Action`` here. Telnet (``CmdCombat``) and the web
``CombatEncounterViewSet`` both reach them through ``dispatch_player_action``;
each ``execute()`` resolves the actor's combat state and calls the existing
service. No new game logic lives here.

``yield`` is intentionally absent: ``YieldAction`` (``definitions/duels.py``)
already exists and is reused by the ``combat yield`` subverb.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist

from actions.base import Action
from actions.constants import ActionCategory
from actions.types import ActionContext, ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatParticipant, CombatRoundAction


def _sheet(actor: ObjectDB) -> CharacterSheet | None:
    """Return *actor*'s CharacterSheet, or None if absent."""
    try:
        return actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None


def _active_combat_participant(
    actor: ObjectDB,
    statuses: set[str],
) -> CombatParticipant | None:
    """Return *actor*'s ACTIVE participant whose encounter is in *statuses*, newest first."""
    from world.combat.constants import ParticipantStatus  # noqa: PLC0415
    from world.combat.models import CombatParticipant  # noqa: PLC0415

    sheet = _sheet(actor)
    if sheet is None:
        return None
    return (
        CombatParticipant.objects.filter(
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
            encounter__status__in=statuses,
        )
        .select_related("encounter")
        .order_by("-encounter__created_at")
        .first()
    )


def _resolve_ally(
    participant: CombatParticipant,
    ally_participant_id: int | None,
) -> CombatParticipant | None:
    """Resolve an ally pk to a CombatParticipant scoped to *participant*'s encounter."""
    if ally_participant_id is None:
        return None
    from world.combat.models import CombatParticipant  # noqa: PLC0415

    return CombatParticipant.objects.filter(
        pk=ally_participant_id,
        encounter=participant.encounter,
    ).first()


def _current_round_action(participant: CombatParticipant) -> CombatRoundAction | None:
    """Return *participant*'s CombatRoundAction for its encounter's current round, or None."""
    from world.combat.models import CombatRoundAction  # noqa: PLC0415

    return CombatRoundAction.objects.filter(
        participant=participant,
        round_number=participant.encounter.round_number,
    ).first()


@dataclass
class FleeAction(Action):
    """Declare a desperate flee — passives-only, auto-ready (wraps ``declare_flee``)."""

    key: str = "combat_flee"
    name: str = "Flee"
    icon: str = "running"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.constants import EncounterStatus  # noqa: PLC0415
        from world.combat.services import declare_flee  # noqa: PLC0415

        participant = _active_combat_participant(actor, {EncounterStatus.DECLARING})
        if participant is None:
            return ActionResult(success=False, message="You are not in an active combat round.")
        try:
            declare_flee(participant)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="You declare a desperate flee.")
