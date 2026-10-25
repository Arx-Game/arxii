"""GM standoff actions (#4354): decide a proposal, move a group's morale, open a standoff.

Account-authorized like the GM prompt actions: ``actor`` may be None (the web dispatches
with the request's account), and every action takes ``account``. Each one checks its own
gate and calls a ``world.standoffs.services`` function; no game logic lives here.

- ``gm_standoff_confirm`` / ``gm_standoff_hold`` / ``gm_standoff_override``: the addressed
  GM (or staff) resolves a ``STANDOFF_CAUSE`` prompt.
- ``gm_standoff_morale``: a scene GM (or staff) moves a group one morale state, SHAKE or
  STEADY, with a required reason. The room gets a plain system line.
- ``gm_open_standoff``: a scene GM (or staff) opens a standoff on an encounter that has not
  begun round one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.prerequisites import Prerequisite
from actions.types import ActionResult, TargetType
from world.standoffs.constants import ProposalResolution

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.combat.models import CombatEncounter

_MSG_NOT_YOURS = "That prompt is not addressed to you."
_MSG_GM_ONLY = "Only the scene's GM or staff can do that."
_MSG_NO_GROUP = "No such standoff group."
_MSG_NO_ENCOUNTER = "No such encounter."


def _account(kwargs: dict[str, Any], actor: ObjectDB | None) -> AccountDB | None:
    account = kwargs.get("account")
    if account is None and actor is not None:
        from commands.utils.gm_resolution import resolve_account_or_none  # noqa: PLC0415

        account = resolve_account_or_none(actor)
    return account


def _may_gm(account: AccountDB | None, encounter: CombatEncounter) -> bool:
    if account is None:
        return False
    if account.is_staff:
        return True
    return encounter.scene is not None and encounter.scene.is_gm(account)


def _announce(encounter: CombatEncounter, *lines: str) -> None:
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    for line in lines:
        if line:
            broadcast_action_outcome(encounter=encounter, narration=line)


@dataclass
class _GMStandoffActionBase(Action):
    category: str = "combat"
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = False

    def get_prerequisites(self) -> list[Prerequisite]:
        return []


@dataclass
class _ResolveProposalAction(_GMStandoffActionBase):
    resolution: str = ""

    def execute(
        self,
        actor: ObjectDB | None,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from core_management.permissions import is_staff_observer  # noqa: PLC0415
        from world.gm.models import GMPrompt  # noqa: PLC0415
        from world.standoffs.services.proposals import resolve_proposal  # noqa: PLC0415

        account = _account(kwargs, actor)
        prompt = (
            GMPrompt.objects.filter(pk=kwargs.get("prompt_id"))
            .select_related("standoff_group__encounter")
            .first()
        )
        if prompt is None or account is None:
            return ActionResult(success=False, message=_MSG_NOT_YOURS)
        if not is_staff_observer(account) and prompt.addressed_to_id != account.pk:
            return ActionResult(success=False, message=_MSG_NOT_YOURS)
        outcome = resolve_proposal(
            prompt,
            self.resolution,
            resolver=account,
            reason=str(kwargs.get("reason") or ""),
        )
        return ActionResult(
            success=outcome.success,
            message=outcome.message,
            data={"prompt_id": prompt.pk, "fight_started": outcome.fight_started},
        )


@dataclass
class GMStandoffConfirmAction(_ResolveProposalAction):
    """The GM confirms a standoff proposal: the group attacks and round one begins."""

    key: str = "gm_standoff_confirm"
    name: str = "Confirm standoff proposal"
    icon: str = "swords"
    resolution: str = ProposalResolution.CONFIRM


@dataclass
class GMStandoffHoldAction(_ResolveProposalAction):
    """The GM holds a proposal for one action; the cause is tested again after it."""

    key: str = "gm_standoff_hold"
    name: str = "Hold standoff proposal"
    icon: str = "pause"
    resolution: str = ProposalResolution.HOLD


@dataclass
class GMStandoffOverrideAction(_ResolveProposalAction):
    """The GM overrides a proposal with a reason; the group stays in the standoff."""

    key: str = "gm_standoff_override"
    name: str = "Override standoff proposal"
    icon: str = "shield"
    resolution: str = ProposalResolution.OVERRIDE


@dataclass
class GMStandoffMoraleAction(_GMStandoffActionBase):
    """A scene GM shakes or steadies a standoff group by one morale state, with a reason."""

    key: str = "gm_standoff_morale"
    name: str = "Move standoff morale"
    icon: str = "activity"

    def execute(
        self,
        actor: ObjectDB | None,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.standoffs.models import StandoffGroup  # noqa: PLC0415
        from world.standoffs.services.gm_morale import shift_group_morale  # noqa: PLC0415

        account = _account(kwargs, actor)
        group = (
            StandoffGroup.objects.filter(pk=kwargs.get("group_id"))
            .select_related("encounter__scene", "creature_template")
            .first()
        )
        if group is None:
            return ActionResult(success=False, message=_MSG_NO_GROUP)
        if not _may_gm(account, group.encounter):
            return ActionResult(success=False, message=_MSG_GM_ONLY)
        outcome = shift_group_morale(
            group,
            str(kwargs.get("direction") or ""),
            str(kwargs.get("reason") or ""),
            ruled_by=account,
        )
        if outcome.success:
            _announce(group.encounter, outcome.room_line, outcome.attack_line)
        return ActionResult(success=outcome.success, message=outcome.message)


@dataclass
class GMOpenStandoffAction(_GMStandoffActionBase):
    """A scene GM opens a standoff on an encounter that has not begun round one."""

    key: str = "gm_open_standoff"
    name: str = "Open a standoff"
    icon: str = "hand"

    def execute(
        self,
        actor: ObjectDB | None,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.models import CombatEncounter  # noqa: PLC0415
        from world.standoffs.services.state import open_standoff  # noqa: PLC0415

        account = _account(kwargs, actor)
        encounter = (
            CombatEncounter.objects.filter(pk=kwargs.get("encounter_id"))
            .select_related("scene")
            .first()
        )
        if encounter is None:
            return ActionResult(success=False, message=_MSG_NO_ENCOUNTER)
        if not _may_gm(account, encounter):
            return ActionResult(success=False, message=_MSG_GM_ONLY)
        if encounter.round_number != 0 or encounter.standoff_groups.exists():
            return ActionResult(
                success=False, message="A standoff opens only before round one, and only once."
            )
        groups = open_standoff(encounter)
        if not groups:
            return ActionResult(
                success=False, message="There is nobody here to hold a standoff with."
            )
        place = encounter.room.db_key if encounter.room is not None else "here"
        _announce(encounter, f"A standoff at {place}.")
        return ActionResult(success=True, message="The standoff is open.")
