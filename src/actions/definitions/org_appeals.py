"""Appeals to organizations (#3293).

Four REGISTRY backend singletons sharing the same seam used by the web
(`dispatch_player_action` / direct `action.run()`) and telnet (`CmdAppeal`).
Mirrors `organizations.py`'s membership-lifecycle actions: each is a thin
wrapper over `world.societies.appeal_services`, translating typed exceptions
into failure `ActionResult`s.
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

    from world.scenes.models import Persona
    from world.societies.models import Organization, OrgAppeal

from world.societies.appeal_services import (
    lodge_appeal,
    resolve_appeal,
    signon_appeal,
    withdraw_appeal,
)
from world.societies.constants import OrgAppealState
from world.societies.exceptions import (
    AppealNotOpenError,
    InvalidAppealVerdictError,
    NotAppealPetitionerError,
    NotAuthorizedToResolveAppealError,
    NotOrganizationMemberError,
)

_MSG_NO_CHARACTER_IDENTITY = "You have no character identity."
_MSG_WHICH_ORGANIZATION = "Which organization?"
_MSG_WHICH_APPEAL = "Which appeal?"
_MSG_TITLE_REQUIRED = "An appeal needs a title."
_MSG_BODY_REQUIRED = "An appeal needs a body."
_MSG_VERDICT_REQUIRED = "Resolve an appeal as either grant or decline."
_MSG_ALREADY_OPEN = "You already have an open appeal with that organization."

_VERDICT_MAP: dict[str, str] = {
    "grant": OrgAppealState.GRANTED,
    "granted": OrgAppealState.GRANTED,
    "decline": OrgAppealState.DECLINED,
    "declined": OrgAppealState.DECLINED,
}


def _actor_sheet(actor: ObjectDB) -> Any:
    try:
        return actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None


def _actor_persona(actor: ObjectDB) -> Persona | None:
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = _actor_sheet(actor)
    if sheet is None:
        return None
    try:
        return active_persona_for_sheet(sheet)
    except ObjectDoesNotExist:
        return None


def _actor_is_staff(actor: ObjectDB) -> bool:
    from world.scenes.scene_admin_services import resolve_actor_account  # noqa: PLC0415

    account = resolve_actor_account(actor)
    return bool(account and account.is_staff)


def _resolve_organization(value: Any) -> Organization | None:
    from world.societies.models import Organization  # noqa: PLC0415

    if value is None:
        return None
    if isinstance(value, Organization):
        return value
    try:
        return Organization.objects.filter(pk=int(value)).first()
    except (TypeError, ValueError):
        return None


def _resolve_appeal(value: Any) -> OrgAppeal | None:
    from world.societies.models import OrgAppeal  # noqa: PLC0415

    if value is None:
        return None
    if isinstance(value, OrgAppeal):
        return value
    try:
        return OrgAppeal.objects.filter(pk=int(value)).select_related("organization").first()
    except (TypeError, ValueError):
        return None


@dataclass
class LodgeAppealAction(Action):
    """Lodge a free-text appeal with an organization. Any character may — no
    membership required."""

    key: str = "org_appeal_lodge"
    name: str = "Lodge Appeal"
    icon: str = "hand-raised"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        actor_persona = _actor_persona(actor)
        if actor_persona is None:
            return ActionResult(success=False, message=_MSG_NO_CHARACTER_IDENTITY)

        organization = _resolve_organization(kwargs.get("organization_id"))
        if organization is None:
            return ActionResult(success=False, message=_MSG_WHICH_ORGANIZATION)

        title = (kwargs.get("title") or "").strip()
        if not title:
            return ActionResult(success=False, message=_MSG_TITLE_REQUIRED)
        body = (kwargs.get("body") or "").strip()
        if not body:
            return ActionResult(success=False, message=_MSG_BODY_REQUIRED)

        from django.db import IntegrityError, transaction  # noqa: PLC0415

        try:
            # The inner atomic() gives the partial-unique-constraint violation
            # its own savepoint: catching IntegrityError without one would
            # otherwise leave the connection's outer transaction aborted for
            # every query that follows (a well-known Django/Postgres trap).
            with transaction.atomic():
                appeal = lodge_appeal(
                    organization=organization,
                    petitioner_persona=actor_persona,
                    title=title,
                    body=body,
                )
        except IntegrityError:
            return ActionResult(success=False, message=_MSG_ALREADY_OPEN)
        return ActionResult(
            success=True,
            message=f"You lodge an appeal with {organization.name}: {title}",
            data={"appeal_id": appeal.pk},
        )


@dataclass
class SignonAppealAction(Action):
    """Sign onto an org member's open appeal to show support."""

    key: str = "org_appeal_signon"
    name: str = "Sign Onto Appeal"
    icon: str = "user-check"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        actor_persona = _actor_persona(actor)
        if actor_persona is None:
            return ActionResult(success=False, message=_MSG_NO_CHARACTER_IDENTITY)

        appeal = _resolve_appeal(kwargs.get("appeal_id"))
        if appeal is None:
            return ActionResult(success=False, message=_MSG_WHICH_APPEAL)

        note = (kwargs.get("note") or "").strip()
        try:
            signon_appeal(appeal=appeal, member_persona=actor_persona, note=note)
        except (AppealNotOpenError, NotOrganizationMemberError) as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"You sign onto the appeal '{appeal.title}'.",
        )


@dataclass
class ResolveAppealAction(Action):
    """Leadership grants or declines an open appeal with a written answer."""

    key: str = "org_appeal_resolve"
    name: str = "Resolve Appeal"
    icon: str = "gavel"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        appeal = _resolve_appeal(kwargs.get("appeal_id"))
        if appeal is None:
            return ActionResult(success=False, message=_MSG_WHICH_APPEAL)

        verdict_token = str(kwargs.get("verdict") or "").strip().lower()
        verdict = _VERDICT_MAP.get(verdict_token)
        if verdict is None:
            return ActionResult(success=False, message=_MSG_VERDICT_REQUIRED)

        actor_persona = _actor_persona(actor)
        is_staff = _actor_is_staff(actor)
        answer = (kwargs.get("answer") or "").strip()

        try:
            resolve_appeal(
                appeal=appeal,
                verdict=verdict,
                resolution_text=answer,
                resolver_persona=actor_persona,
                is_staff=is_staff,
            )
        except (
            AppealNotOpenError,
            InvalidAppealVerdictError,
            NotAuthorizedToResolveAppealError,
        ) as exc:
            return ActionResult(success=False, message=exc.user_message)

        verb = "grant" if verdict == OrgAppealState.GRANTED else "decline"
        return ActionResult(
            success=True,
            message=f"You {verb} the appeal '{appeal.title}'.",
        )


@dataclass
class WithdrawAppealAction(Action):
    """Withdraw your own open appeal."""

    key: str = "org_appeal_withdraw"
    name: str = "Withdraw Appeal"
    icon: str = "x-circle"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        actor_persona = _actor_persona(actor)
        if actor_persona is None:
            return ActionResult(success=False, message=_MSG_NO_CHARACTER_IDENTITY)

        appeal = _resolve_appeal(kwargs.get("appeal_id"))
        if appeal is None:
            return ActionResult(success=False, message=_MSG_WHICH_APPEAL)

        try:
            withdraw_appeal(appeal=appeal, petitioner_persona=actor_persona)
        except (AppealNotOpenError, NotAppealPetitionerError) as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"You withdraw your appeal '{appeal.title}'.",
        )


# Module-level singletons registered in actions.registry.
org_appeal_lodge_action = LodgeAppealAction()
org_appeal_signon_action = SignonAppealAction()
org_appeal_resolve_action = ResolveAppealAction()
org_appeal_withdraw_action = WithdrawAppealAction()
