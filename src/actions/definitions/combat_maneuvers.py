"""Combat maneuver actions on the shared dispatch seam (#1453, #1452).

Each verb a player can take in a fight that is not a technique cast or a clash
commit — flee, cover, interpose, succor, ready, join/leave the encounter, and the
combo upgrade/revert — is a real ``Action`` here. Telnet (``CmdCombat``) and the web
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
    from world.combat.models import CombatEncounter, CombatParticipant, CombatRoundAction
    from world.magic.models import Technique

# Repeated ActionResult failure messages, extracted to satisfy S1192.
NOT_IN_ACTIVE_ROUND_MESSAGE = "You are not in an active combat round."
NO_ACTION_DECLARED_MESSAGE = "You have not declared an action yet."


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


def _resolve_technique(technique_id: int | None) -> Technique | None:
    """Resolve a technique pk to a Technique instance, or None when not supplied."""
    if technique_id is None:
        return None
    from world.magic.models import Technique  # noqa: PLC0415

    return Technique.objects.filter(pk=technique_id).first()


def _resolve_opponent(
    participant: CombatParticipant,
    opponent_id: int | None,
) -> object | None:
    """Resolve an opponent pk to a CombatOpponent scoped to *participant*'s encounter."""
    if opponent_id is None:
        return None
    from world.combat.models import CombatOpponent  # noqa: PLC0415

    return CombatOpponent.objects.filter(
        pk=opponent_id,
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
        from world.combat.services import declare_flee  # noqa: PLC0415
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        participant = _active_combat_participant(actor, {RoundStatus.DECLARING})
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_ACTIVE_ROUND_MESSAGE)
        try:
            declare_flee(participant)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="You declare a desperate flee.")


@dataclass
class CoverAction(Action):
    """Cover an ally — passives-only, auto-ready (wraps ``declare_cover``)."""

    key: str = "combat_cover"
    name: str = "Cover"
    icon: str = "shield"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        ally_participant_id: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import declare_cover  # noqa: PLC0415
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        participant = _active_combat_participant(actor, {RoundStatus.DECLARING})
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_ACTIVE_ROUND_MESSAGE)
        if ally_participant_id is None:
            return ActionResult(success=False, message="Cover requires an ally to protect.")
        ally = _resolve_ally(participant, ally_participant_id)
        if ally is None:
            return ActionResult(success=False, message="No such ally in this encounter.")
        try:
            declare_cover(participant, ally)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="You move to cover your ally.")


@dataclass
class InterposeAction(Action):
    """Interpose to guard an ally (or any ally) — passives-only (wraps ``declare_interpose``)."""

    key: str = "combat_interpose"
    name: str = "Interpose"
    icon: str = "shield-half"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        ally_participant_id: int | None = None,
        technique_id: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import declare_interpose  # noqa: PLC0415
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        participant = _active_combat_participant(actor, {RoundStatus.DECLARING})
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_ACTIVE_ROUND_MESSAGE)
        ally = _resolve_ally(participant, ally_participant_id)
        if ally_participant_id is not None and ally is None:
            return ActionResult(success=False, message="No such ally in this encounter.")
        technique = _resolve_technique(technique_id)
        if technique_id is not None and technique is None:
            return ActionResult(success=False, message="No such technique.")
        try:
            declare_interpose(participant, ally, technique=technique)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="You stand ready to interpose.")


@dataclass
class SuccorAction(Action):
    """Shelter a specific ally from environmental hazards (wraps ``declare_succor``)."""

    key: str = "combat_succor"
    name: str = "Succor"
    icon: str = "umbrella"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        ally_participant_id: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import declare_succor  # noqa: PLC0415
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        participant = _active_combat_participant(actor, {RoundStatus.DECLARING})
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_ACTIVE_ROUND_MESSAGE)
        if ally_participant_id is None:
            return ActionResult(success=False, message="Succor requires an ally to shelter.")
        ally = _resolve_ally(participant, ally_participant_id)
        if ally is None:
            return ActionResult(success=False, message="No such ally in this encounter.")
        try:
            declare_succor(participant, ally)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="You move to shelter your ally.")


def _resolve_held_item_instance(
    actor: ObjectDB,
    item_name: str | None,
    item_instance_id: int | None,
) -> Any:
    """Resolve the item to use — by explicit id (web) or held-item name (telnet, #2120).

    ``item_instance_id`` (web) is looked up directly; ``item_name`` (telnet) is
    resolved by searching only the actor's own held items -- mirrors ``CmdUse``'s
    ``self.search_or_raise`` (``evennia_overrides/items.py``), but scoped to
    ``location=actor`` rather than the room+inventory default, since a used item
    must be held. Returns ``None`` when nothing resolves; actual possession is
    re-validated by ``declare_use_item``.
    """
    from actions.definitions.item_helpers import resolve_item_instance  # noqa: PLC0415
    from world.items.models import ItemInstance  # noqa: PLC0415

    if item_instance_id is not None:
        return ItemInstance.objects.filter(pk=item_instance_id).first()
    if not item_name:
        return None
    found = actor.search(item_name, location=actor, quiet=True)
    if isinstance(found, list):
        found = found[0] if found else None
    if found is None:
        return None
    return resolve_item_instance(found)


@dataclass
class UseItemManeuverAction(Action):
    """Declare using a held on-use item as this round's action (wraps ``declare_use_item``, #2120).

    A primary maneuver -- mutually exclusive with a declared focused technique,
    unlike the passives-only FLEE/COVER/INTERPOSE/SUCCOR maneuvers above. The item
    is resolved either by ``item_instance_id`` (web) or by ``item_name`` (telnet,
    searched among the actor's own held items). The optional target may be an
    ally (``ally_participant_id``) or an opponent (``opponent_id``); at most one
    should be supplied.
    """

    key: str = "combat_use"
    name: str = "Use Item"
    icon: str = "flask-conical"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    def execute(  # noqa: PLR0913
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        item_name: str | None = None,
        item_instance_id: int | None = None,
        ally_participant_id: int | None = None,
        opponent_id: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import declare_use_item  # noqa: PLC0415
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        participant = _active_combat_participant(actor, {RoundStatus.DECLARING})
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_ACTIVE_ROUND_MESSAGE)

        item_instance = _resolve_held_item_instance(actor, item_name, item_instance_id)
        if item_instance is None:
            return ActionResult(success=False, message="Use what?")

        target: object | None = None
        if ally_participant_id is not None:
            target = _resolve_ally(participant, ally_participant_id)
            if target is None:
                return ActionResult(success=False, message="No such ally in this encounter.")
        elif opponent_id is not None:
            target = _resolve_opponent(participant, opponent_id)
            if target is None:
                return ActionResult(success=False, message="No such opponent in this encounter.")

        try:
            declare_use_item(participant, item_instance, target=target)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message=f"You use {item_instance}.")


@dataclass
class ReadyAction(Action):
    """Toggle your declared action's ready flag (wraps ``toggle_action_ready``)."""

    key: str = "combat_ready"
    name: str = "Ready"
    icon: str = "check"
    category: str = "combat"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import (  # noqa: PLC0415
            maybe_resolve_on_ready,
            toggle_action_ready,
        )
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        participant = _active_combat_participant(actor, {RoundStatus.DECLARING})
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_ACTIVE_ROUND_MESSAGE)
        action = _current_round_action(participant)
        if action is None:
            return ActionResult(success=False, message=NO_ACTION_DECLARED_MESSAGE)
        toggle_action_ready(action)
        if not action.is_ready:
            return ActionResult(success=True, message="You are no longer ready.")
        # #2120: in PaceMode.READY, this may be the last participant to ready
        # — check whether the round should resolve now rather than wait out
        # the TIMED sweep. Un-readying (handled above) never triggers this.
        maybe_resolve_on_ready(participant.encounter)
        return ActionResult(success=True, message="You are ready.")


@dataclass
class UpgradeComboAction(Action):
    """Chain your declared action into a combo (#1452, wraps ``upgrade_action_to_combo``)."""

    key: str = "combat_combo"
    name: str = "Combo"
    icon: str = "layers"
    category: str = "combat"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        combo_id: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.models import ComboDefinition  # noqa: PLC0415
        from world.combat.services import upgrade_action_to_combo  # noqa: PLC0415
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        participant = _active_combat_participant(actor, {RoundStatus.DECLARING})
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_ACTIVE_ROUND_MESSAGE)
        action = _current_round_action(participant)
        if action is None:
            return ActionResult(success=False, message=NO_ACTION_DECLARED_MESSAGE)
        combo = ComboDefinition.objects.filter(pk=combo_id).first() if combo_id else None
        if combo is None:
            return ActionResult(success=False, message="No such combo.")
        try:
            upgrade_action_to_combo(action, combo)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        # Changing the declared action un-readies it (mirrors the former inline view logic).
        action.is_ready = False
        action.save(update_fields=["is_ready"])
        return ActionResult(success=True, message=f"You chain into {combo.name}.")


@dataclass
class RevertComboAction(Action):
    """Revert a combo upgrade on your declared action (wraps ``revert_combo_upgrade``)."""

    key: str = "combat_revert"
    name: str = "Revert Combo"
    icon: str = "undo"
    category: str = "combat"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import revert_combo_upgrade  # noqa: PLC0415
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        participant = _active_combat_participant(actor, {RoundStatus.DECLARING})
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_ACTIVE_ROUND_MESSAGE)
        action = _current_round_action(participant)
        if action is None:
            return ActionResult(success=False, message=NO_ACTION_DECLARED_MESSAGE)
        try:
            revert_combo_upgrade(action)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        action.is_ready = False
        action.save(update_fields=["is_ready"])
        return ActionResult(success=True, message="You revert the combo.")


def _active_encounter_in_room(actor: ObjectDB) -> CombatEncounter | None:
    """Return the newest joinable encounter in *actor*'s room, or None (telnet join path)."""
    from world.combat.models import CombatEncounter  # noqa: PLC0415
    from world.scenes.constants import RoundStatus  # noqa: PLC0415

    room = actor.location
    if room is None:
        return None
    return (
        CombatEncounter.objects.filter(
            room=room,
            status__in={RoundStatus.DECLARING, RoundStatus.BETWEEN_ROUNDS},
        )
        .order_by("-created_at")
        .first()
    )


@dataclass
class JoinEncounterAction(Action):
    """Join an active combat encounter (wraps ``join_encounter``).

    ``encounter_id`` / ``character_sheet_id`` are supplied by the web (the URL pk
    and the request-validated sheet); telnet omits both and the encounter is the
    one in the caller's room, joined as the caller's own character.
    """

    key: str = "combat_join"
    name: str = "Join Combat"
    icon: str = "user-plus"
    category: str = "combat"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        encounter_id: int | None = None,
        character_sheet_id: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
        from world.combat.models import CombatEncounter  # noqa: PLC0415
        from world.combat.services import join_encounter  # noqa: PLC0415

        if character_sheet_id is not None:
            sheet = CharacterSheet.objects.filter(pk=character_sheet_id).first()
        else:
            sheet = _sheet(actor)
        if sheet is None:
            return ActionResult(success=False, message="You have no character to join with.")

        if encounter_id is not None:
            encounter = CombatEncounter.objects.filter(pk=encounter_id).first()
        else:
            encounter = _active_encounter_in_room(actor)
        if encounter is None:
            return ActionResult(success=False, message="There is no encounter to join here.")

        try:
            join_encounter(encounter, sheet)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="You join the fight.")


@dataclass
class LeaveEncounterAction(Action):
    """Leave an open encounter between rounds (wraps ``leave_encounter``)."""

    key: str = "combat_leave"
    name: str = "Leave Combat"
    icon: str = "user-minus"
    category: str = "combat"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import leave_encounter  # noqa: PLC0415
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        participant = _active_combat_participant(actor, {RoundStatus.BETWEEN_ROUNDS})
        if participant is None:
            return ActionResult(
                success=False,
                message="You are not in an encounter you can leave right now.",
            )
        try:
            leave_encounter(participant)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="You withdraw from the fight.")


@dataclass
class EngageAction(Action):
    """Challenge an NPC — adds threat to trigger an engagement lock (#2020).

    The PC calls ``accumulate_threat`` with ``amount = opponent.auto_lock_threshold + 1``,
    guaranteeing the pairing crosses threshold on the next ``select_npc_actions``
    pass. The NPC "accepts" by the threshold crossing.
    """

    key: str = "combat_engage"
    name: str = "Engage"
    icon: str = "swords"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.engagement_locks import (  # noqa: PLC0415
            create_engagement_lock_for_challenge,
        )
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        participant = _active_combat_participant(actor, {RoundStatus.DECLARING})
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_ACTIVE_ROUND_MESSAGE)

        opponent_id = kwargs.get("opponent_id")
        if opponent_id is None:
            return ActionResult(success=False, message="You must specify an opponent to engage.")

        try:
            create_engagement_lock_for_challenge(participant, opponent_id)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="You challenge your opponent to a duel!")


@dataclass
class DisengageAction(Action):
    """Break your active engagement lock (#2020)."""

    key: str = "combat_disengage"
    name: str = "Disengage"
    icon: str = "shield-off"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.constants import (  # noqa: PLC0415
            EngagementLockStatus,
            LockBreakReason,
        )
        from world.combat.engagement_locks import break_engagement_lock  # noqa: PLC0415
        from world.combat.models import EngagementLock  # noqa: PLC0415
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        participant = _active_combat_participant(actor, {RoundStatus.DECLARING})
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_ACTIVE_ROUND_MESSAGE)

        active_lock = EngagementLock.objects.filter(
            participant=participant,
            status=EngagementLockStatus.ACTIVE,
        ).first()
        if active_lock is None:
            return ActionResult(success=False, message="You are not engaged in a duel.")
        break_engagement_lock(active_lock, reason=LockBreakReason.DISENGAGE)
        return ActionResult(success=True, message="You disengage from the duel.")


@dataclass
class RallyAction(Action):
    """Rally an ally — inspire them for the round (wraps ``declare_rally``)."""

    key: str = "combat_rally"
    name: str = "Rally"
    icon: str = "megaphone"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        ally_participant_id: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import declare_rally  # noqa: PLC0415
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        participant = _active_combat_participant(actor, {RoundStatus.DECLARING})
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_ACTIVE_ROUND_MESSAGE)
        if ally_participant_id is None:
            return ActionResult(success=False, message="Rally requires an ally to inspire.")
        ally = _resolve_ally(participant, ally_participant_id)
        if ally is None:
            return ActionResult(success=False, message="No such ally in this encounter.")
        try:
            declare_rally(participant, ally)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="You rally your ally.")


@dataclass
class DemoralizeAction(Action):
    """Demoralize an opponent — break their nerve (wraps ``declare_demoralize``)."""

    key: str = "combat_demoralize"
    name: str = "Demoralize"
    icon: str = "frown"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        opponent_id: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import declare_demoralize  # noqa: PLC0415
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        participant = _active_combat_participant(actor, {RoundStatus.DECLARING})
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_ACTIVE_ROUND_MESSAGE)
        opponent = _resolve_opponent(participant, opponent_id)
        if opponent is None:
            return ActionResult(success=False, message="No such opponent in this encounter.")
        try:
            declare_demoralize(participant, opponent)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="You move to demoralize your foe.")


@dataclass
class TauntAction(Action):
    """Taunt an opponent — draw their aggro (wraps ``declare_taunt``)."""

    key: str = "combat_taunt"
    name: str = "Taunt"
    icon: str = "target"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        opponent_id: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import declare_taunt  # noqa: PLC0415
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        participant = _active_combat_participant(actor, {RoundStatus.DECLARING})
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_ACTIVE_ROUND_MESSAGE)
        opponent = _resolve_opponent(participant, opponent_id)
        if opponent is None:
            return ActionResult(success=False, message="No such opponent in this encounter.")
        try:
            declare_taunt(participant, opponent)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="You taunt your foe.")


@dataclass
class ParleyAction(Action):
    """Parley with an opponent — talk them down (wraps ``declare_parley``)."""

    key: str = "combat_parley"
    name: str = "Parley"
    icon: str = "comments"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        opponent_id: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import declare_parley  # noqa: PLC0415
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        participant = _active_combat_participant(actor, {RoundStatus.DECLARING})
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_ACTIVE_ROUND_MESSAGE)
        opponent = _resolve_opponent(participant, opponent_id)
        if opponent is None:
            return ActionResult(success=False, message="No such opponent in this encounter.")
        try:
            declare_parley(participant, opponent)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="You attempt to parley with your foe.")
