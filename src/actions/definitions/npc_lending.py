"""Lending a major NPC (#4418): offer, answer, take back, ask to borrow.

Thin web-only wrappers over ``world.roster.services.npc_lending``; the service owns
every rule and raises ``NPCLendingError`` with a player-safe message. Telnet has no
verb for these; it only reaches a lent NPC through the existing ``@ic`` switch.

The acting account is the one puppeting the actor, else the actor's tenure holder,
so a Guide acting from the NPC they were lent still acts as the Guide.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import IsGuidePrerequisite, IsSceneGMPrerequisite, Prerequisite
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext

NO_ACCOUNT_MESSAGE = "No account is playing this character."
NO_SUCH_LOAN_MESSAGE = "No such loan."
NO_SUCH_NPC_MESSAGE = "No such NPC."


def _acting_account(actor: ObjectDB) -> AccountDB | None:
    from commands.utils.gm_resolution import resolve_account_or_none  # noqa: PLC0415

    return actor.account or resolve_account_or_none(actor)


def _int_kwarg(kwargs: dict[str, Any], name: str) -> int | None:
    try:
        return int(kwargs.get(name))
    except (TypeError, ValueError):
        return None


def _loan(kwargs: dict[str, Any]):
    from world.roster.models import NPCLoan  # noqa: PLC0415

    loan_id = _int_kwarg(kwargs, "loan_id")
    if loan_id is None:
        return None
    return (
        NPCLoan.objects.filter(pk=loan_id)
        .select_related("roster_entry__character_sheet__character", "scene", "borrower")
        .first()
    )


def _entry(kwargs: dict[str, Any]):
    from world.roster.models import RosterEntry  # noqa: PLC0415

    entry_id = _int_kwarg(kwargs, "roster_entry_id")
    if entry_id is None:
        return None
    return (
        RosterEntry.objects.filter(pk=entry_id)
        .select_related("roster", "character_sheet__character")
        .first()
    )


def _loan_result(loan, message: str) -> ActionResult:
    return ActionResult(
        success=True,
        message=message,
        data={"loan_id": loan.pk, "status": loan.status},
    )


@dataclass
class _NPCLendingAction(Action):
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF


@dataclass
class OfferNPCAction(_NPCLendingAction):
    """The scene's GM offers an NPC they own to a Guide for this scene.

    Kwargs: ``roster_entry_id``, ``guide_account_id``.
    """

    key: str = "offer_npc"
    name: str = "Lend NPC"
    icon: str = "user-share"

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsSceneGMPrerequisite()]

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from evennia.accounts.models import AccountDB  # noqa: PLC0415

        from world.roster.services.npc_lending import NPCLendingError, offer_npc  # noqa: PLC0415
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

        account = _acting_account(actor)
        if account is None:
            return ActionResult(success=False, message=NO_ACCOUNT_MESSAGE)
        entry = _entry(kwargs)
        if entry is None:
            return ActionResult(success=False, message=NO_SUCH_NPC_MESSAGE)
        guide_id = _int_kwarg(kwargs, "guide_account_id")
        guide = AccountDB.objects.filter(pk=guide_id).first() if guide_id else None
        if guide is None:
            return ActionResult(success=False, message="No such Guide.")
        scene = get_active_scene(actor.location)
        if scene is None:
            return ActionResult(success=False, message="There is no scene here.")
        try:
            loan = offer_npc(entry=entry, guide=guide, scene=scene, by=account)
        except NPCLendingError as exc:
            return ActionResult(success=False, message=exc.user_message)
        name = entry.character_sheet.character.db_key
        return _loan_result(loan, f"{name} is offered for {scene.name}.")


@dataclass
class AnswerNPCLoanAction(_NPCLendingAction):
    """Accept or decline a loan: a Guide answers an offer, an owner a request.

    Kwargs: ``loan_id``, ``accept`` (bool).
    """

    key: str = "answer_npc_loan"
    name: str = "Answer NPC Loan"
    icon: str = "user-check"

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsGuidePrerequisite(or_gm=True)]

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.roster.services.npc_lending import NPCLendingError, answer_loan  # noqa: PLC0415

        account = _acting_account(actor)
        if account is None:
            return ActionResult(success=False, message=NO_ACCOUNT_MESSAGE)
        loan = _loan(kwargs)
        if loan is None:
            return ActionResult(success=False, message=NO_SUCH_LOAN_MESSAGE)
        accept = kwargs.get("accept") is True
        try:
            loan = answer_loan(loan=loan, accept=accept, by=account)
        except NPCLendingError as exc:
            return ActionResult(success=False, message=exc.user_message)
        name = loan.roster_entry.character_sheet.character.db_key
        message = f"You take up {name}." if accept else f"You turn down {name}."
        if accept and loan.borrower_id != account.pk:
            message = f"{name} is lent."
        return _loan_result(loan, message)


@dataclass
class TakeBackNPCAction(_NPCLendingAction):
    """End a loan: the owner takes the NPC back, or the borrower hands it back.

    Kwargs: ``loan_id``.
    """

    key: str = "take_back_npc"
    name: str = "Take Back NPC"
    icon: str = "user-minus"

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.roster.services.npc_lending import NPCLendingError, end_loan  # noqa: PLC0415

        account = _acting_account(actor)
        if account is None:
            return ActionResult(success=False, message=NO_ACCOUNT_MESSAGE)
        loan = _loan(kwargs)
        if loan is None:
            return ActionResult(success=False, message=NO_SUCH_LOAN_MESSAGE)
        try:
            end_loan(loan, by=account)
        except NPCLendingError as exc:
            return ActionResult(success=False, message=exc.user_message)
        name = loan.roster_entry.character_sheet.character.db_key
        return _loan_result(loan, f"{name} is back with their owner.")


@dataclass
class RequestNPCBorrowAction(_NPCLendingAction):
    """A GM or Guide asks to borrow an NPC from the NPC roster.

    Kwargs: ``roster_entry_id``.
    """

    key: str = "request_npc_borrow"
    name: str = "Ask to Borrow NPC"
    icon: str = "user-question"

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsGuidePrerequisite(or_gm=True)]

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.roster.constants import NPCLoanStatus  # noqa: PLC0415
        from world.roster.services.npc_lending import (  # noqa: PLC0415
            NPCLendingError,
            request_borrow,
        )

        account = _acting_account(actor)
        if account is None:
            return ActionResult(success=False, message=NO_ACCOUNT_MESSAGE)
        entry = _entry(kwargs)
        if entry is None:
            return ActionResult(success=False, message=NO_SUCH_NPC_MESSAGE)
        try:
            loan = request_borrow(entry=entry, borrower=account)
        except NPCLendingError as exc:
            return ActionResult(success=False, message=exc.user_message)
        name = entry.character_sheet.character.db_key
        if loan.status == NPCLoanStatus.ACTIVE:
            return _loan_result(loan, f"You take up {name}.")
        return _loan_result(loan, f"You ask to borrow {name}.")
