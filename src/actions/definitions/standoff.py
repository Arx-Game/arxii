"""Standoff actions on the shared dispatch seam (#4145).

Read, press, name terms, fight and share a spark are registry ``Action`` verbs. Telnet
(``CmdStandoff``) and the web reach them through ``dispatch_player_action``; each
``execute()`` resolves the actor's participant in a standoff, scopes the group to that
encounter and calls the ``world.standoffs.services.verbs`` service. No game logic lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.definitions.combat_maneuvers import _sheet
from actions.types import ActionContext, ActionResult, TargetType
from world.standoffs.constants import FIGHT_BEGINS_MESSAGE, SUCCESS_LEVEL_WORDS

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.combat.models import CombatParticipant
    from world.standoffs.models import StandoffApproach, StandoffGroup, StandoffTerms
    from world.standoffs.types import StandoffActionResult

NOT_IN_STANDOFF_MESSAGE = "You are not in a standoff."
_NO_SUCH_GROUP_MSG = "No such group in this standoff."


def _standoff_participant(actor: ObjectDB) -> CombatParticipant | None:
    """The actor's ACTIVE participant in an encounter that is in its standoff, newest first."""
    from world.combat.constants import ParticipantStatus  # noqa: PLC0415
    from world.combat.models import CombatParticipant  # noqa: PLC0415
    from world.standoffs.services.state import is_in_standoff  # noqa: PLC0415

    sheet = _sheet(actor)
    if sheet is None:
        return None
    candidates = (
        CombatParticipant.objects.filter(character_sheet=sheet, status=ParticipantStatus.ACTIVE)
        .select_related("encounter")
        .order_by("-encounter__created_at")
    )
    return next((p for p in candidates if is_in_standoff(p.encounter)), None)


def _resolve_group(participant: CombatParticipant, group_id: int | None) -> StandoffGroup | None:
    """Resolve a group pk, scoped to the participant's encounter."""
    if group_id is None:
        return None
    from world.standoffs.models import StandoffGroup  # noqa: PLC0415

    return StandoffGroup.objects.filter(pk=group_id, encounter=participant.encounter).first()


def _to_result(outcome: StandoffActionResult) -> ActionResult:
    """The actor's message; a verb that set the creatures on them says so."""
    message = outcome.message
    if outcome.fight_started and message != FIGHT_BEGINS_MESSAGE:
        message = f"{message} They attack!"
    data: dict[str, Any] = {}
    warning = outcome.soulfray_warning
    if warning is not None:
        # The web picker shows this and re-sends the press with confirm_soulfray_risk.
        data["soulfray_warning"] = {
            "stage_name": warning.stage_name,
            "stage_description": warning.stage_description,
            "has_death_risk": warning.has_death_risk,
        }
    return ActionResult(success=outcome.success, message=message, data=data)


def _announce(participant: CombatParticipant, line: str, outcome: StandoffActionResult) -> None:
    """Tell the room what the verb was, once it actually happened (not when it was refused).

    The line names the actor, the verb, the group and a plain outcome word, and nothing the
    verb learned or any hidden profile detail: reveals travel only in the reader's own
    message and the party payload.
    """
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    if not outcome.success and outcome.success_level is None:
        return
    broadcast_action_outcome(encounter=participant.encounter, narration=line, deliver_telnet=True)
    if outcome.morale_line:
        broadcast_action_outcome(
            encounter=participant.encounter,
            narration=outcome.morale_line,
            deliver_telnet=True,
        )
    if outcome.attack_line:
        broadcast_action_outcome(
            encounter=participant.encounter,
            narration=outcome.attack_line,
            deliver_telnet=True,
        )


def _reaction_or_plain(
    participant: CombatParticipant,
    group: StandoffGroup,
    parent: StandoffApproach | StandoffTerms,
    outcome: StandoffActionResult,
    plain: str,
) -> str:
    """The authored reaction line for this roll, or the plain line when none applies."""
    from world.standoffs.services.reactions import reaction_text  # noqa: PLC0415

    if outcome.success_level is None:
        return plain
    authored = reaction_text(
        parent,
        creature_template_id=group.creature_template_id,
        group_name=group.creature_template.name,
        actor_name=_actor_label(participant),
        success_level=outcome.success_level,
    )
    return authored or plain


def _actor_label(participant: CombatParticipant) -> str:
    """The name the actor is presenting under, never the character's true key."""
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    return active_persona_for_sheet(participant.character_sheet).name


def _outcome_word(outcome: StandoffActionResult) -> str:
    """The same five-tier word the actor's own message opens with, in lower case."""
    if outcome.success_level is None:
        return "success" if outcome.success else "failure"
    return SUCCESS_LEVEL_WORDS[max(-2, min(2, outcome.success_level))].lower()


def _read_result(
    outcome: StandoffActionResult, group: StandoffGroup, participant: CombatParticipant
) -> ActionResult:
    """A read's message carries what the reader learned, as they may know it."""
    from world.standoffs.services.describe import describe_reveals  # noqa: PLC0415

    lines = describe_reveals(group, outcome.revealed, participant.character_sheet)
    return ActionResult(success=outcome.success, message="\n".join([outcome.message, *lines]))


@dataclass
class StandoffReadAction(Action):
    """Read a group of opponents for what drives them (wraps ``standoff_read``)."""

    key: str = "standoff_read"
    name: str = "Read"
    icon: str = "eye"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    def execute(  # noqa: PLR0913 - the focus kwargs are the read verb's whole payload
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        group_id: int | None = None,
        focus_kind: str | None = None,
        focus_drive_id: int | None = None,
        focus_regard_rule_id: int | None = None,
        focus_property_id: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.standoffs.services.verbs import standoff_read  # noqa: PLC0415

        participant = _standoff_participant(actor)
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_STANDOFF_MESSAGE)
        group = _resolve_group(participant, group_id)
        if group is None:
            return ActionResult(success=False, message=_NO_SUCH_GROUP_MSG)
        outcome = standoff_read(
            participant,
            group,
            focus_kind=focus_kind,
            focus_drive_id=focus_drive_id,
            focus_regard_rule_id=focus_regard_rule_id,
            focus_property_id=focus_property_id,
        )
        _announce(
            participant,
            f"{_actor_label(participant)} reads the {group.creature_template.name}: "
            f"{_outcome_word(outcome)}.",
            outcome,
        )
        return _read_result(outcome, group, participant)


@dataclass
class StandoffPressAction(Action):
    """Press a group with a social approach (wraps ``standoff_press``)."""

    key: str = "standoff_press"
    name: str = "Press"
    icon: str = "hand"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    def execute(  # noqa: PLR0913 - the press kwargs are the verb's whole payload
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        group_id: int | None = None,
        approach_id: int | None = None,
        technique_id: int | None = None,
        confirm_soulfray_risk: bool = False,
        **kwargs: Any,
    ) -> ActionResult:
        from world.magic.models import Technique  # noqa: PLC0415
        from world.standoffs.models import StandoffApproach  # noqa: PLC0415
        from world.standoffs.services.verbs import standoff_press  # noqa: PLC0415

        participant = _standoff_participant(actor)
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_STANDOFF_MESSAGE)
        group = _resolve_group(participant, group_id)
        if group is None:
            return ActionResult(success=False, message=_NO_SUCH_GROUP_MSG)
        approach = StandoffApproach.objects.filter(pk=approach_id).first()
        if approach is None:
            return ActionResult(success=False, message="No such approach.")
        technique = (
            None if technique_id is None else Technique.objects.filter(pk=technique_id).first()
        )
        if technique_id is not None and technique is None:
            return ActionResult(success=False, message="No such technique.")
        outcome = standoff_press(
            participant, group, approach, technique, confirm_soulfray_risk=confirm_soulfray_risk
        )
        plain = (
            f"{_actor_label(participant)} presses the {group.creature_template.name} "
            f"with {approach.name}: {_outcome_word(outcome)}."
        )
        _announce(
            participant, _reaction_or_plain(participant, group, approach, outcome, plain), outcome
        )
        return _to_result(outcome)


@dataclass
class StandoffTermsAction(Action):
    """Name terms to a group (wraps ``standoff_terms``)."""

    key: str = "standoff_terms"
    name: str = "Name terms"
    icon: str = "handshake"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        group_id: int | None = None,
        terms_id: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.standoffs.models import StandoffTerms  # noqa: PLC0415
        from world.standoffs.services.verbs import standoff_terms  # noqa: PLC0415

        participant = _standoff_participant(actor)
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_STANDOFF_MESSAGE)
        group = _resolve_group(participant, group_id)
        if group is None:
            return ActionResult(success=False, message=_NO_SUCH_GROUP_MSG)
        terms = StandoffTerms.objects.filter(pk=terms_id).first()
        if terms is None:
            return ActionResult(success=False, message="No such terms.")
        outcome = standoff_terms(participant, group, terms)
        plain = (
            f"{_actor_label(participant)} names {terms.name} to "
            f"the {group.creature_template.name}: {_outcome_word(outcome)}."
        )
        _announce(
            participant, _reaction_or_plain(participant, group, terms, outcome, plain), outcome
        )
        return _to_result(outcome)


@dataclass
class StandoffFightAction(Action):
    """Break the standoff and begin the fight (wraps ``standoff_fight``)."""

    key: str = "standoff_fight"
    name: str = "Fight"
    icon: str = "swords"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.standoffs.services.verbs import standoff_fight  # noqa: PLC0415

        participant = _standoff_participant(actor)
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_STANDOFF_MESSAGE)
        outcome = standoff_fight(participant, participant.encounter)
        _announce(participant, f"{_actor_label(participant)} breaks the standoff.", outcome)
        return _to_result(outcome)


@dataclass
class StandoffShareSparkAction(Action):
    """Share what your character feels about a group (wraps ``standoff_share_spark``)."""

    key: str = "standoff_share_spark"
    name: str = "Share a spark"
    icon: str = "sparkles"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        group_id: int | None = None,
        regard_rule_id: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.standoffs.models import RegardRule  # noqa: PLC0415
        from world.standoffs.services.verbs import standoff_share_spark  # noqa: PLC0415

        participant = _standoff_participant(actor)
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_STANDOFF_MESSAGE)
        group = _resolve_group(participant, group_id)
        if group is None:
            return ActionResult(success=False, message=_NO_SUCH_GROUP_MSG)
        rule = RegardRule.objects.filter(
            pk=regard_rule_id, creature_template_id=group.creature_template_id
        ).first()
        if rule is None:
            return ActionResult(success=False, message="That does not apply to you.")
        outcome = standoff_share_spark(participant, group, rule)
        _announce(
            participant,
            f"{_actor_label(participant)} shares what they feel about "
            f"the {group.creature_template.name}.",
            outcome,
        )
        return _to_result(outcome)
